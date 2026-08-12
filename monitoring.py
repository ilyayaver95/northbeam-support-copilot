#!/usr/bin/env python3
"""monitoring.py — KPIs, and the regression gate between versions.

"How do I know this works, and how would I prove it?" has two answers, and they
come from different places at different moments:

  QUALITY       from graded eval runs (`evals/run_all.py --save`). Did it get
                the right answer? These decide whether a change ships.
  OPERATIONAL   from the trace log written on every `ask()`. Is it fast, cheap
                and stable? These tell you something is degrading in production,
                where nothing is labelled.

Usage:
    python monitoring.py ops                          # operational KPIs
    python monitoring.py ops --version abc123         # scope to one version
    python monitoring.py quality after.json           # quality KPIs
    python monitoring.py compare before.json after.json   # A/B with a gate

`compare` exits non-zero when any category regresses beyond --tolerance, so it
works unchanged as a CI gate on a pull request.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Sequence

from observability import load_traces

# How many cases a category may lose without failing the gate. Zero tolerates no
# regression; one absorbs single-case jitter on temperature-locked models, which
# is also what --samples is for.
DEFAULT_TOLERANCE = 0


def pct(numerator: int, denominator: int) -> float:
    return 100.0 * numerator / denominator if denominator else 0.0


def quantile(values: Sequence[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))
    return ordered[index]


def _row(label: str, value: str, note: str = "") -> str:
    return f"  {label:<34}{value:>14}  {note}"


# ---------------------------------------------------------------------------
# Operational KPIs
# ---------------------------------------------------------------------------


def operational_kpis(traces: list[dict[str, Any]]) -> dict[str, Any]:
    if not traces:
        return {}

    # Cache hits are ~0ms and 0 steps. Letting them into the latency series would
    # make a slow system look fast just by re-running the same suite.
    live = [t for t in traces if not t.get("cached")]
    latencies = [t.get("total_ms", 0.0) for t in live]
    errors = [t for t in traces if t.get("error")]
    declines = [t for t in traces if t.get("declined")]
    by_code = [t for t in declines if t.get("decision_source") == "code"]
    tool_counts = [len(t.get("tools_used") or []) for t in live]
    answered = [t for t in traces if not t.get("declined")]

    return {
        "n_calls": len(traces),
        "n_uncached": len(live),
        "cache_hit_rate_pct": round(pct(len(traces) - len(live), len(traces)), 1),
        "error_rate_pct": round(pct(len(errors), len(traces)), 2),
        "latency_p50_ms": round(quantile(latencies, 0.50)),
        "latency_p95_ms": round(quantile(latencies, 0.95)),
        "latency_max_ms": round(max(latencies)) if latencies else 0,
        "mean_steps": round(statistics.fmean(t.get("steps", 0) for t in live), 2) if live else 0,
        "step_limit_rate_pct": round(
            pct(sum(1 for t in live if t.get("hit_step_limit")), len(live)), 1),
        "mean_tool_calls": round(statistics.fmean(tool_counts), 2) if tool_counts else 0,
        "no_tool_rate_pct": round(pct(sum(1 for n in tool_counts if n == 0),
                                      len(tool_counts)), 1),
        "forced_tool_rate_pct": round(
            pct(sum(1 for t in live if t.get("forced_tool_use")), len(live)), 1),
        "tool_error_rate_pct": round(
            pct(sum(t.get("tool_errors", 0) for t in live), max(1, sum(tool_counts))), 1),
        "decline_rate_pct": round(pct(len(declines), len(traces)), 1),
        "declines_in_code_pct": round(pct(len(by_code), len(declines)), 1),
        "uncited_rate_pct": round(
            pct(sum(1 for t in answered if not t.get("n_sources")), len(answered)), 1),
        "bad_citation_rate_pct": round(
            pct(sum(1 for t in traces if t.get("bad_sources")), len(traces)), 1),
        "mean_tokens": round(statistics.fmean(
            t.get("prompt_tokens", 0) + t.get("completion_tokens", 0)
            for t in live), 1) if live else 0,
    }


def tool_histogram(traces: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trace in traces:
        for name in trace.get("tools_used") or []:
            counts[name] = counts.get(name, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def rule_histogram(traces: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trace in traces:
        rule = trace.get("decision_rule") or ""
        if rule:
            counts[rule] = counts.get(rule, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def cmd_ops(args: argparse.Namespace) -> int:
    traces = load_traces(args.path)
    if args.version:
        traces = [t for t in traces if t.get("version") == args.version]
    if args.last:
        traces = traces[-args.last:]
    if not traces:
        print("No traces yet. Ask a question first — every ask() writes one line "
              "to traces/traces.jsonl.")
        return 0

    kpis = operational_kpis(traces)
    if args.json:
        print(json.dumps({"kpis": kpis, "tools": tool_histogram(traces),
                          "rules": rule_histogram(traces)}, indent=2))
        return 0

    versions = sorted({t.get("version", "?") for t in traces})
    print("\n" + "=" * 68)
    print(f"  OPERATIONAL KPIs   ({kpis['n_calls']} calls · {', '.join(versions)})")
    print("=" * 68)
    print(_row("latency p50", f"{kpis['latency_p50_ms']} ms"))
    print(_row("latency p95", f"{kpis['latency_p95_ms']} ms", "the tail a user feels"))
    print(_row("mean tool calls / answer", f"{kpis['mean_tool_calls']}"))
    print(_row("mean loop steps", f"{kpis['mean_steps']}"))
    print(_row("step limit hit", f"{kpis['step_limit_rate_pct']}%",
               "raise MAX_STEPS if this climbs"))
    print(_row("answers with no tool call", f"{kpis['no_tool_rate_pct']}%",
               "ungrounded — should stay near zero"))
    print(_row("tool use forced", f"{kpis['forced_tool_rate_pct']}%",
               "tried to answer with no evidence"))
    print(_row("tool error rate", f"{kpis['tool_error_rate_pct']}%", "bad ids or args"))
    print(_row("uncited answers", f"{kpis['uncited_rate_pct']}%"))
    print(_row("malformed citations", f"{kpis['bad_citation_rate_pct']}%",
               "cited something with no valid id shape"))
    print(_row("decline rate", f"{kpis['decline_rate_pct']}%"))
    print(_row("  ...decided in code", f"{kpis['declines_in_code_pct']}%",
               "vs left to model judgment"))
    print(_row("error rate", f"{kpis['error_rate_pct']}%"))
    print(_row("cache hit rate", f"{kpis['cache_hit_rate_pct']}%"))
    print(_row("mean tokens / answer", f"{kpis['mean_tokens']}", "cost proxy"))

    tools = tool_histogram(traces)
    if tools:
        print("\n  tool usage:")
        for name, n in tools.items():
            print(f"    {name:<24}{n:>5}")
    rules = rule_histogram(traces)
    if rules:
        print("\n  outcome decided by:")
        for name, n in rules.items():
            print(f"    {name:<28}{n:>5}")
    print()
    return 0


# ---------------------------------------------------------------------------
# Quality KPIs
# ---------------------------------------------------------------------------


def quality_kpis(run: dict[str, Any]) -> dict[str, Any]:
    """Headline quality numbers from a run_all.py --save payload."""
    scores = run.get("scores", {})
    passed = sum(s["passed"] for s in scores.values())
    total = sum(s["total"] for s in scores.values())
    out = {
        "pass_rate_pct": round(pct(passed, total), 1),
        "passed": passed,
        "total": total,
        "per_category": {c: round(pct(s["passed"], s["total"]), 1)
                         for c, s in scores.items()},
    }
    out.update(run.get("behaviour", {}))
    return out


def cmd_quality(args: argparse.Namespace) -> int:
    run = json.loads(Path(args.run).read_text())
    kpis = quality_kpis(run)
    if args.json:
        print(json.dumps(kpis, indent=2))
        return 0

    print("\n" + "=" * 68)
    print(f"  QUALITY KPIs   ({args.run} · {run.get('version', '?')} · "
          f"samples={run.get('samples', 1)})")
    print("=" * 68)
    print(_row("overall pass rate", f"{kpis['pass_rate_pct']}%",
               f"{kpis['passed']}/{kpis['total']} cases"))
    for category, value in kpis["per_category"].items():
        print(_row(f"  {category}", f"{value}%"))
    print()
    for label, key, note in [
        ("over-decline rate", "over_decline_pct", "refused something answerable"),
        ("under-decline rate", "under_decline_pct", "answered something to refuse"),
        ("hedge rate", "hedge_pct", "vague where a fact was expected"),
        ("citation coverage", "citation_coverage_pct", "answers citing a source"),
        ("tool coverage", "tool_coverage_pct", "answers grounded in a tool result"),
        ("malformed citations", "bad_citation_pct", "cited an invalid id"),
    ]:
        if key in kpis:
            print(_row(label, f"{kpis[key]}%", note))
    print()
    return 0


# ---------------------------------------------------------------------------
# A/B comparison and the regression gate
# ---------------------------------------------------------------------------


def compare_runs(base: dict[str, Any], candidate: dict[str, Any],
                 tolerance: int = DEFAULT_TOLERANCE) -> dict[str, Any]:
    """Diff two saved eval runs. `regressions` drives the exit code."""
    base_scores = base.get("scores", {})
    candidate_scores = candidate.get("scores", {})

    rows, regressions = [], []
    for category in sorted(set(base_scores) | set(candidate_scores)):
        before, after = base_scores.get(category), candidate_scores.get(category)
        if not before or not after:
            rows.append({"category": category, "delta": None,
                         "note": "present in only one run"})
            continue
        delta = after["passed"] - before["passed"]
        rows.append({
            "category": category,
            "base": f"{before['passed']}/{before['total']}",
            "candidate": f"{after['passed']}/{after['total']}",
            "delta": delta,
        })
        if delta < -tolerance:
            regressions.append({"category": category, "delta": delta})

    return {
        "rows": rows,
        "total_delta": (sum(s["passed"] for s in candidate_scores.values())
                        - sum(s["passed"] for s in base_scores.values())),
        "regressions": regressions,
        "tolerance": tolerance,
    }


def cmd_compare(args: argparse.Namespace) -> int:
    base = json.loads(Path(args.baseline).read_text())
    candidate = json.loads(Path(args.candidate).read_text())
    result = compare_runs(base, candidate, tolerance=args.tolerance)

    if args.json:
        print(json.dumps(result, indent=2))
        return 1 if result["regressions"] else 0

    print("\n" + "=" * 70)
    print(f"  A/B   {base.get('version', args.baseline)}  ->  "
          f"{candidate.get('version', args.candidate)}")
    print("=" * 70)
    print(f"  {'category':<26}{'base':>10}{'candidate':>12}{'delta':>8}")
    print("  " + "-" * 56)
    for row in result["rows"]:
        if row["delta"] is None:
            print(f"  {row['category']:<26}{'—':>10}{'—':>12}{'—':>8}  {row['note']}")
            continue
        delta = row["delta"]
        shown = f"+{delta}" if delta > 0 else str(delta)
        print(f"  {row['category']:<26}{row['base']:>10}{row['candidate']:>12}{shown:>8}")
    print("  " + "-" * 56)
    total = result["total_delta"]
    print(f"  {'TOTAL':<26}{'':>10}{'':>12}"
          f"{('+' + str(total)) if total > 0 else total:>8}")

    if result["regressions"]:
        print(f"\n  FAILED (tolerance {args.tolerance}): " + ", ".join(
            f"{r['category']} {r['delta']}" for r in result["regressions"]))
        print("  Do not ship this change as-is.\n")
        return 1
    print("\n  PASSED — no category regressed.\n")
    return 0


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    ops = sub.add_parser("ops", help="operational KPIs from the trace log")
    ops.add_argument("--path", default=None, help="trace file, default traces/traces.jsonl")
    ops.add_argument("--version", default=None, help="only traces with this version tag")
    ops.add_argument("--last", type=int, default=None, help="only the last N traces")
    ops.add_argument("--json", action="store_true")
    ops.set_defaults(func=cmd_ops)

    quality = sub.add_parser("quality", help="quality KPIs from a saved eval run")
    quality.add_argument("run", help="JSON written by evals/run_all.py --save")
    quality.add_argument("--json", action="store_true")
    quality.set_defaults(func=cmd_quality)

    compare = sub.add_parser("compare", help="A/B two saved runs; exits 1 on regression")
    compare.add_argument("baseline")
    compare.add_argument("candidate")
    compare.add_argument("--tolerance", type=int, default=DEFAULT_TOLERANCE,
                         help="cases a category may lose without failing the gate")
    compare.add_argument("--json", action="store_true")
    compare.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
