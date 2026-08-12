"""aggregate.py — the calculation layer.

Every tool in `records.py` answers "tell me about ONE thing". Questions like

    "which operator had the most failed dispatches this month?"
    "how many cases are still open and due before the end of the month?"
    "what's the total downtime across Cape Solvang's fleet?"
    "which open case has the largest parts cost?"

need filtering, grouping and arithmetic over a whole dataset. Without this the
model has to hold 213 unit records in its context and add them up in prose,
which is precisely where language models are least reliable.

The split: the **model** decides what to compute — which dataset, which filters,
which metric. **Python** computes it. No arithmetic ever happens in the model's
head, so counts and totals are reproducible and can be unit-tested against the
data. Every result carries:

  - the value
  - the ids of the records behind it, so the answer stays citable
  - a `computation` string describing exactly what ran, so it can be audited by
    a human reading the evidence
"""
from __future__ import annotations

from typing import Any, Callable

from . import store

# Cap on returned records, so a sweep over 213 units cannot flood the evidence
# block and push the real question out of the context window.
MAX_RECORDS = 25

METRICS = ("count", "sum", "avg", "min", "max", "list")

# ISO dates and numbers both order correctly under plain Python comparison, so
# no per-type special casing is needed. Type mismatches are caught, not raised.
OPS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in (a or []),
    "starts_with": lambda a, b: isinstance(a, str) and a.startswith(b),
    "exists": lambda a, b: (a is not None) == bool(b),
}


def known_fields(dataset: str) -> set[str]:
    """Every field path that exists on any record in a dataset.

    Records are heterogeneous — an event may or may not carry `unit_id` or
    `metadata` — so this is the union across all of them, including one level of
    dotted paths into nested metadata.
    """
    fields: set[str] = set()
    for record in store.load(dataset):
        for key, value in record.items():
            fields.add(key)
            if isinstance(value, dict):
                fields.update(f"{key}.{inner}" for inner in value)
    return fields


def _validate_fields(dataset: str, names: list[str]) -> str | None:
    """Reject a field that exists on no record, naming what does exist.

    Without this, a filter on a misspelt or imagined field ("status" on a
    dataset that calls it "response_logged") quietly matches nothing and the
    tool returns a confident zero. A silently wrong number is far worse than an
    error, because the model will happily report it — so this is the one place
    the calculation layer is allowed to refuse to compute.
    """
    available = known_fields(dataset)
    unknown = [n for n in names if n and n not in available]
    if not unknown:
        return None
    return (f"unknown field(s) {unknown} on dataset {dataset!r}. "
            f"Available fields: {', '.join(sorted(available))}")


def _matches(record: dict, filters: list[dict]) -> bool:
    for f in filters:
        name = f.get("field")
        op = f.get("op", "eq")
        if not name:
            raise ValueError("every filter needs a 'field'")
        if op not in OPS:
            raise ValueError(f"unknown op {op!r}; choose one of {', '.join(OPS)}")
        actual = store.field(record, name)
        if actual is None and op not in ("exists", "ne", "not_in"):
            return False
        try:
            if not OPS[op](actual, f.get("value")):
                return False
        except TypeError:
            # e.g. a string field compared against a number. Treat as no match
            # rather than aborting the whole sweep.
            return False
    return True


def aggregate_records(
    dataset: str,
    metric: str = "count",
    field: str | None = None,
    filters: list[dict] | None = None,
    group_by: str | None = None,
    sort: str = "desc",
    limit: int = 10,
) -> dict:
    """Filter, group and compute across a whole dataset. Deterministic; no LLM maths.

    Args:
        dataset: "operators" | "units" | "cases" | "events" | "tickets".
        metric: "count" | "sum" | "avg" | "min" | "max" | "list". Everything
                except count and list needs `field`.
        field: the numeric field to compute over, e.g. "downtime_minutes_30d",
               "parts_cost_cents", "availability_30d". Dotted paths reach into
               event metadata, e.g. "metadata.availability_30d".
        filters: list of {"field", "op", "value"}, AND-ed together. ISO dates
                 compare as plain strings, so
                 {"field": "sla_response_due", "op": "lte", "value": "2026-09-30"}
                 does what it looks like.
        group_by: field to group on before computing, e.g. "operator_id" or
                  "event_type". Groups come back ranked by their value — this is
                  how "which operator has the most X" is answered.
        sort: "desc" (default) or "asc".
        limit: max groups or records returned.

    Returns:
        {"dataset", "metric", "field", "matched", "computation",
         "value" | "groups", "records", "truncated"}
        or {"error": "..."} — never a partial or guessed number.
    """
    filters = filters or []

    try:
        rows = store.load(dataset)
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}

    if metric not in METRICS:
        return {"error": f"unknown metric {metric!r}; choose one of {', '.join(METRICS)}"}
    if metric in ("sum", "avg", "min", "max") and not field:
        return {"error": f"metric {metric!r} needs a numeric 'field'"}

    referenced = [f.get("field") for f in filters] + [field, group_by]
    problem = _validate_fields(dataset, [r for r in referenced if r])
    if problem:
        return {"error": problem}

    try:
        matched = [r for r in rows if _matches(r, filters)]
    except ValueError as e:
        return {"error": str(e)}

    limit = max(1, min(int(limit or 10), MAX_RECORDS))

    def compute(records: list[dict]) -> Any:
        if metric in ("count", "list"):
            return len(records)
        values = [v for v in (store.field(r, field) for r in records)
                  if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if not values:
            return None
        if metric == "sum":
            return sum(values)
        if metric == "avg":
            return round(sum(values) / len(values), 6)
        return min(values) if metric == "min" else max(values)

    described = " and ".join(
        f"{f['field']} {f.get('op', 'eq')} {f.get('value')!r}" for f in filters
    ) or "no filter"

    result: dict[str, Any] = {
        "dataset": dataset,
        "metric": metric,
        "field": field,
        "filters": filters,
        "matched": len(matched),
    }

    if group_by:
        buckets: dict[Any, list[dict]] = {}
        for record in matched:
            buckets.setdefault(store.field(record, group_by), []).append(record)

        groups = [{"key": key,
                   "value": compute(rs),
                   "count": len(rs),
                   "ids": [r["id"] for r in rs][:MAX_RECORDS]}
                  for key, rs in buckets.items()]

        # Groups with an undefined metric sort last in BOTH directions — an empty
        # group must never win a "which is largest" question.
        ranked = [g for g in groups if g["value"] is not None]
        ranked.sort(key=lambda g: g["value"], reverse=(sort == "desc"))
        ranked += [g for g in groups if g["value"] is None]

        result["groups"] = ranked[:limit]
        result["group_count"] = len(groups)
        result["computation"] = (
            f"{metric}({field or '*'}) over {dataset} where {described}, grouped by "
            f"{group_by} — {len(groups)} group(s) across {len(matched)} record(s)")
    else:
        result["value"] = compute(matched)
        result["computation"] = (
            f"{metric}({field or '*'}) over {dataset} where {described} "
            f"— {len(matched)} record(s) matched")

    # Always return the underlying records (capped) so an answer can cite real
    # ids instead of asserting a bare number.
    shown = matched
    if field:
        numeric = [r for r in shown
                   if isinstance(store.field(r, field), (int, float))]
        numeric.sort(key=lambda r: store.field(r, field), reverse=(sort == "desc"))
        shown = numeric + [r for r in shown if r not in numeric]
    result["records"] = shown[:limit]
    result["truncated"] = len(matched) > len(result["records"])

    return result
