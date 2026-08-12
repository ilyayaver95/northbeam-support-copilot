"""The KPI maths, the trace log, and the regression gate.

A monitoring layer that reports wrong numbers is worse than none, because you
would ship on it. And a gate that never fails is decoration — so the failing
path is tested as carefully as the passing one.
"""
from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from monitoring import (
    compare_runs, operational_kpis, quality_kpis, rule_histogram, tool_histogram,
)
from observability import Trace, load_traces, question_id, record


def trace(**overrides) -> dict:
    base = dict(question="q", model="m", total_ms=100.0, steps=1,
                tools_used=["get_case"])
    base.update(overrides)
    return asdict(Trace(**base))


# ---------------------------------------------------------------------------
# operational KPIs
# ---------------------------------------------------------------------------


def test_an_empty_log_yields_nothing_rather_than_dividing_by_zero():
    assert operational_kpis([]) == {}


def test_latency_percentiles():
    kpis = operational_kpis([trace(total_ms=float(x)) for x in range(1, 101)])
    assert kpis["latency_p50_ms"] == pytest.approx(50, abs=1)
    assert kpis["latency_p95_ms"] == pytest.approx(95, abs=1)
    assert kpis["latency_max_ms"] == 100


def test_cached_calls_are_kept_out_of_the_latency_series():
    """Cache hits are ~0ms. Letting them in would make a slow system look fast
    just by re-running the same suite twice."""
    traces = ([trace(total_ms=1000.0, steps=3)] * 2
              + [trace(total_ms=1.0, steps=0, cached=True)] * 8)
    kpis = operational_kpis(traces)
    assert kpis["cache_hit_rate_pct"] == 80.0
    assert kpis["latency_p50_ms"] == 1000
    assert kpis["mean_steps"] == 3.0


def test_error_and_step_limit_rates():
    kpis = operational_kpis([trace(), trace(error="Timeout"),
                             trace(hit_step_limit=True), trace()])
    assert kpis["error_rate_pct"] == 25.0
    assert kpis["step_limit_rate_pct"] == 25.0


def test_ungrounded_answer_rate():
    kpis = operational_kpis([trace(tools_used=[]), trace(tools_used=["get_case"])])
    assert kpis["no_tool_rate_pct"] == 50.0


def test_the_code_versus_model_split_is_reported():
    traces = [
        trace(declined=True, decision_source="code", decision_rule="protected_value"),
        trace(declined=True, decision_source="code", decision_rule="state_change_action"),
        trace(declined=True, decision_source="model", decision_rule="model_judgment"),
        trace(declined=False),
    ]
    kpis = operational_kpis(traces)
    assert kpis["decline_rate_pct"] == 75.0
    assert kpis["declines_in_code_pct"] == pytest.approx(66.7, abs=0.1)
    assert rule_histogram(traces)["protected_value"] == 1


def test_uncited_rate_counts_only_answered_calls():
    """A decline citing nothing is fine; an ANSWER citing nothing is the problem."""
    traces = [trace(declined=True, n_sources=0),
              trace(declined=False, n_sources=0),
              trace(declined=False, n_sources=2)]
    assert operational_kpis(traces)["uncited_rate_pct"] == 50.0


def test_tool_histogram_counts_repeats():
    traces = [trace(tools_used=["a", "b", "a"]), trace(tools_used=["a"])]
    assert tool_histogram(traces) == {"a": 3, "b": 1}


# ---------------------------------------------------------------------------
# the trace log
# ---------------------------------------------------------------------------


def test_traces_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("TRACE_LOG_PATH", str(path))
    record(Trace(question="how many open cases?", model="m", total_ms=12.0))
    record(Trace(question="another", model="m", total_ms=8.0))

    loaded = load_traces(path)
    assert len(loaded) == 2
    assert loaded[0]["question"] == "how many open cases?"
    assert loaded[0]["qid"], "traces need a stable id to join runs across versions"


def test_the_same_question_gets_the_same_id():
    assert question_id("What is the target?") == question_id("what  IS the target?")
    assert Trace(question="a").qid != Trace(question="b").qid


def test_tracing_can_be_turned_off(tmp_path, monkeypatch):
    path = tmp_path / "traces.jsonl"
    monkeypatch.setenv("TRACE_LOG_PATH", str(path))
    monkeypatch.setenv("TRACE_LOG", "0")
    record(Trace(question="q"))
    assert not path.exists()


def test_recording_never_raises_into_the_caller(tmp_path, monkeypatch):
    """Telemetry that can break the answer path is worse than no telemetry."""
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    monkeypatch.setenv("TRACE_LOG_PATH", str(blocker / "sub" / "traces.jsonl"))
    record(Trace(question="q"))          # must not raise


def test_malformed_lines_are_skipped_not_fatal(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text('{"question": "ok"}\nnot json at all\n{"question": "also ok"}\n')
    assert len(load_traces(path)) == 2


# ---------------------------------------------------------------------------
# quality KPIs and the gate
# ---------------------------------------------------------------------------


def run(**categories) -> dict:
    return {"scores": {k: {"passed": p, "total": t} for k, (p, t) in categories.items()}}


def test_quality_kpis_aggregate_across_categories():
    kpis = quality_kpis(run(boundaries=(18, 20), investigation=(12, 15)))
    assert kpis["passed"] == 30 and kpis["total"] == 35
    assert kpis["pass_rate_pct"] == pytest.approx(85.7, abs=0.1)
    assert kpis["per_category"]["boundaries"] == 90.0


def test_behaviour_kpis_survive_the_round_trip():
    payload = run(boundaries=(18, 20))
    payload["behaviour"] = {"over_decline_pct": 5.0, "under_decline_pct": 0.0}
    assert quality_kpis(payload)["over_decline_pct"] == 5.0


def test_the_gate_passes_when_nothing_regressed():
    result = compare_runs(run(a=(5, 10)), run(a=(8, 10)))
    assert result["regressions"] == []
    assert result["total_delta"] == 3


def test_the_gate_fails_on_a_regression_even_when_the_total_improved():
    """The trade this exists to catch: a change that lifts the headline number
    while quietly breaking boundaries. Per-category, never just the total."""
    result = compare_runs(run(boundaries=(20, 20), investigation=(5, 15)),
                          run(boundaries=(16, 20), investigation=(14, 15)))
    assert result["total_delta"] > 0
    assert [r["category"] for r in result["regressions"]] == ["boundaries"]


def test_tolerance_absorbs_single_case_jitter():
    before, after = run(a=(10, 10)), run(a=(9, 10))
    assert compare_runs(before, after, tolerance=0)["regressions"]
    assert not compare_runs(before, after, tolerance=1)["regressions"]


def test_a_category_in_only_one_run_is_flagged_not_ignored():
    result = compare_runs(run(a=(1, 1)), run(a=(1, 1), b=(1, 1)))
    row = next(r for r in result["rows"] if r["category"] == "b")
    assert row["delta"] is None and row["note"]


def test_saved_run_files_compare_end_to_end(tmp_path):
    before, after = tmp_path / "before.json", tmp_path / "after.json"
    before.write_text(json.dumps({"version": "v1", **run(boundaries=(14, 20))}))
    after.write_text(json.dumps({"version": "v2", **run(boundaries=(19, 20))}))
    result = compare_runs(json.loads(before.read_text()), json.loads(after.read_text()))
    assert result["total_delta"] == 5 and not result["regressions"]


def test_forced_tool_use_is_reported():
    """The guard in copilot.gather_evidence fires when the first turn tries to
    answer with no evidence. If it starts firing often, the prompt has drifted."""
    traces = [trace(forced_tool_use=True), trace(), trace(), trace()]
    assert operational_kpis(traces)["forced_tool_rate_pct"] == 25.0
