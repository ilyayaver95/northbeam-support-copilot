"""The calculation layer, checked against the data itself.

Expected values are computed here from the raw files rather than pasted in as
literals, so these stay true when the world is regenerated. What is being tested
is that `aggregate_records` computes what a straightforward Python loop would —
which is exactly what the model can no longer get wrong.

Several cases cross-check against `data/generated_facts.json`, the ground truth
the generator wrote. If the aggregation layer and the generator disagree, one of
them is broken and this says so.
"""
from __future__ import annotations

import json

import pytest

from tools import store
from tools.aggregate import aggregate_records


@pytest.fixture(scope="module")
def facts() -> dict:
    return store.facts()


@pytest.fixture(scope="module")
def operators() -> dict:
    return json.loads((store.DATA_DIR / "operators.json").read_text())


@pytest.fixture(scope="module")
def units() -> dict:
    return json.loads((store.DATA_DIR / "units.json").read_text())


@pytest.fixture(scope="module")
def cases() -> dict:
    return json.loads((store.DATA_DIR / "cases.json").read_text())


@pytest.fixture(scope="module")
def events() -> list[dict]:
    text = (store.DATA_DIR / "event_log.jsonl").read_text()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# counting
# ---------------------------------------------------------------------------


def test_counts_every_record(units):
    assert aggregate_records("units", "count")["value"] == len(units)


def test_filtered_count_matches_a_manual_count(units):
    expected = sum(1 for u in units.values() if u["status"] == "operational")
    result = aggregate_records(
        "units", "count",
        filters=[{"field": "status", "op": "eq", "value": "operational"}])
    assert result["value"] == expected
    assert result["matched"] == expected


def test_no_matches_is_zero_not_none():
    result = aggregate_records(
        "units", "count",
        filters=[{"field": "status", "op": "eq", "value": "imaginary"}])
    assert result["value"] == 0
    assert result["records"] == []


# ---------------------------------------------------------------------------
# the aggregation questions the eval suite actually asks
# ---------------------------------------------------------------------------


def test_open_cases_due_by_month_end(facts):
    """investigation_012: open, still inside the window, due on or before month end."""
    result = aggregate_records(
        "cases", "count",
        filters=[
            {"field": "response_logged", "op": "eq", "value": False},
            {"field": "sla_response_due", "op": "gte", "value": facts["today"]},
            {"field": "sla_response_due", "op": "lte", "value": facts["month_end"]},
        ])
    assert result["value"] == facts["open_cases_due_by_month_end"]["count"]


def test_largest_open_case_comes_back_with_its_id(facts, cases):
    """investigation_014: the biggest open case, and which one it is."""
    expected = facts["largest_open_case"]
    result = aggregate_records(
        "cases", "max", field="parts_cost_cents",
        filters=[{"field": "response_logged", "op": "eq", "value": False}],
        limit=1)
    assert result["value"] == expected["parts_cost_cents"]
    # A bare number can't be cited — the id has to come back too.
    assert result["records"][0]["case_id"] == expected["case_id"]


def test_most_failed_dispatches_by_operator(facts, events):
    """investigation_011: which operator, and how many."""
    counts: dict[str, int] = {}
    for event in events:
        if event["event_type"] == "dispatch_failed":
            counts[event["operator_id"]] = counts.get(event["operator_id"], 0) + 1

    result = aggregate_records(
        "events", "count",
        filters=[{"field": "event_type", "op": "eq", "value": "dispatch_failed"}],
        group_by="operator_id")

    top = result["groups"][0]
    assert top["key"] == facts["most_failed_dispatches"]["operator_id"]
    assert top["value"] == facts["most_failed_dispatches"]["count"]
    assert top["value"] == counts[top["key"]]


def test_operators_at_or_below_the_availability_threshold(facts, operators):
    """investigation_013, including the deliberate near-miss."""
    result = aggregate_records(
        "operators", "list",
        filters=[{"field": "availability_30d", "op": "lte", "value": 0.995}],
        limit=25)
    found = {r["operator_id"] for r in result["records"]}

    assert found == set(facts["operators_at_or_below_995"]["operator_ids"])

    # OP-2764 sits at 0.9952, just above the line. A >= / <= slip puts it in.
    near_miss = facts["operators_at_or_below_995"]["near_miss"]["operator_id"]
    assert near_miss not in found
    assert operators[near_miss]["availability_30d"] > 0.995


def test_case_count_per_operator(facts):
    result = aggregate_records("cases", "count", group_by="operator_id", limit=25)
    assert ({g["key"]: g["value"] for g in result["groups"]}
            == facts["case_counts_by_operator"])


def test_only_one_case_has_breached_its_window(facts, cases):
    """The CS-8312 trap has to be unique, or investigation_001 stops being sharp."""
    result = aggregate_records(
        "cases", "list",
        filters=[
            {"field": "response_logged", "op": "eq", "value": False},
            {"field": "sla_response_due", "op": "lt", "value": facts["today"]},
        ],
        limit=25)
    breached = sorted(r["case_id"] for r in result["records"])
    assert breached == facts["breached_sla_cases"] == ["CS-8312"]


# ---------------------------------------------------------------------------
# arithmetic
# ---------------------------------------------------------------------------


def test_sum_matches_a_manual_total(units):
    expected = sum(u["downtime_minutes_30d"] for u in units.values()
                   if u["operator_id"] == "OP-2742")
    result = aggregate_records(
        "units", "sum", field="downtime_minutes_30d",
        filters=[{"field": "operator_id", "op": "eq", "value": "OP-2742"}])
    assert result["value"] == expected


def test_min_max_and_average_agree_with_python(operators):
    values = [o["availability_30d"] for o in operators.values()]
    assert aggregate_records("operators", "max", field="availability_30d")["value"] == max(values)
    assert aggregate_records("operators", "min", field="availability_30d")["value"] == min(values)
    assert aggregate_records("operators", "avg", field="availability_30d")["value"] == pytest.approx(
        sum(values) / len(values), abs=1e-6)


def test_booleans_are_not_counted_as_numbers():
    """response_logged is a bool. Summing it would silently treat True as 1."""
    result = aggregate_records("cases", "sum", field="response_logged")
    assert result["value"] is None


# ---------------------------------------------------------------------------
# ranking, dates, nesting
# ---------------------------------------------------------------------------


def test_groups_are_ranked_and_direction_is_honoured(units):
    kwargs = dict(dataset="units", metric="sum", field="downtime_minutes_30d",
                  group_by="operator_id", limit=25)
    descending = [g["value"] for g in aggregate_records(**kwargs)["groups"]]
    ascending = [g["value"] for g in aggregate_records(**kwargs, sort="asc")["groups"]]

    assert descending == sorted(descending, reverse=True)
    assert ascending == sorted(ascending)

    # `limit` truncates the two rankings from opposite ends, so the lists differ.
    # What must hold is that the extremes are the true extremes.
    totals: dict[str, int] = {}
    for unit in units.values():
        totals[unit["operator_id"]] = (
            totals.get(unit["operator_id"], 0) + unit["downtime_minutes_30d"])
    assert descending[0] == max(totals.values())
    assert ascending[0] == min(totals.values())


def test_iso_dates_compare_as_plain_strings(events):
    """A cutoff drawn from the data itself, so this survives regeneration."""
    dates = sorted(e["timestamp"][:10] for e in events)
    cutoff = dates[len(dates) // 2]
    expected = sum(1 for e in events if e["timestamp"][:10] >= cutoff)
    result = aggregate_records(
        "events", "count",
        filters=[{"field": "date", "op": "gte", "value": cutoff}])
    assert result["value"] == expected
    assert 0 < expected < len(events), "cutoff must actually split the data"


def test_dotted_paths_reach_event_metadata():
    result = aggregate_records(
        "events", "count",
        filters=[{"field": "metadata.availability_30d", "op": "exists", "value": True}])
    assert result["value"] >= 1


def test_result_describes_what_it_computed(facts):
    result = aggregate_records(
        "cases", "count",
        filters=[{"field": "sla_response_due", "op": "lte",
                  "value": facts["month_end"]}])
    # The evidence block must show WHAT ran, not just the number.
    assert "count" in result["computation"]
    assert "sla_response_due" in result["computation"]


# ---------------------------------------------------------------------------
# bad input must never yield a plausible-looking number
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kwargs", [
    {"dataset": "nonsense", "metric": "count"},
    {"dataset": "cases", "metric": "median"},
    {"dataset": "cases", "metric": "sum"},                              # no field
    {"dataset": "cases", "metric": "count",
     "filters": [{"field": "severity", "op": "matches", "value": "x"}]},
    {"dataset": "cases", "metric": "count", "filters": [{"op": "eq", "value": 1}]},
])
def test_bad_input_returns_an_error_never_a_value(kwargs):
    result = aggregate_records(**kwargs)
    assert "error" in result
    assert "value" not in result and "groups" not in result


def test_an_unknown_field_errors_instead_of_silently_matching_nothing():
    """Regression. A filter on a field that exists on no record used to match
    zero and return a confident zero, which the model then reported as the
    answer. A silently wrong number is worse than an error, so this is the one
    place the calculation layer refuses to compute."""
    result = aggregate_records(
        "cases", "max", field="parts_cost_cents",
        filters=[{"field": "status", "op": "eq", "value": "open"}])
    assert "error" in result
    assert "status" in result["error"]
    # The error has to name what IS available, or the model cannot recover.
    assert "response_logged" in result["error"]
    assert "value" not in result


@pytest.mark.parametrize("kwargs", [
    {"dataset": "cases", "metric": "max", "field": "imaginary_cost"},
    {"dataset": "cases", "metric": "count", "group_by": "imaginary_group"},
])
def test_unknown_metric_and_group_fields_are_caught_too(kwargs):
    assert "error" in aggregate_records(**kwargs)


def test_known_fields_covers_nested_metadata():
    from tools.aggregate import known_fields
    fields = known_fields("events")
    assert "event_type" in fields and "operator_id" in fields
    assert any(f.startswith("metadata.") for f in fields)


def test_valid_fields_still_pass_validation():
    """The guard must not reject legitimate queries — including dotted paths."""
    assert "error" not in aggregate_records(
        "events", "count",
        filters=[{"field": "metadata.availability_30d", "op": "exists", "value": True}])
    assert "error" not in aggregate_records(
        "cases", "max", field="parts_cost_cents", group_by="operator_id",
        filters=[{"field": "response_logged", "op": "eq", "value": False}])


def test_comparing_a_string_field_to_a_number_does_not_crash():
    result = aggregate_records(
        "cases", "count",
        filters=[{"field": "fault_code", "op": "gt", "value": 5}])
    assert result["value"] == 0


def test_returned_records_are_capped():
    result = aggregate_records("units", "list", limit=1000)
    assert len(result["records"]) <= 25
    assert result["truncated"] is True
