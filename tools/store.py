"""store.py — the single place that reads `data/` off disk.

Every tool goes through here, so there is one cache, one path resolution, and one
normalization rule. Records come back with their own id under a stable `id` key
*and* under their natural key name (`unit_id`, `case_id`, …), which is what lets
the aggregation layer group and cite without special-casing each dataset.

Read-only by construction: `load()` hands out deep copies of list contents, so a
tool that mutates what it got back cannot corrupt the cache for the next call.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

# dataset -> (filename, natural key name)
DATASETS: dict[str, tuple[str, str]] = {
    "operators": ("operators.json", "operator_id"),
    "units": ("units.json", "unit_id"),
    "cases": ("cases.json", "case_id"),
    "events": ("event_log.jsonl", "event_id"),
    "tickets": ("tickets_index.json", "ticket_id"),
}

_cache: dict[str, list[dict]] = {}


def _read(dataset: str) -> list[dict]:
    filename, key_name = DATASETS[dataset]
    path = DATA_DIR / filename

    if filename.endswith(".jsonl"):
        rows = []
        for i, line in enumerate(path.read_text().splitlines()):
            if not line.strip():
                continue
            record = json.loads(line)
            # `date` is derived so date filters work identically on every dataset:
            # plain YYYY-MM-DD string comparison.
            rows.append({
                "id": f"EV-{i:04d}",
                key_name: f"EV-{i:04d}",
                "date": record.get("timestamp", "")[:10],
                **record,
            })
        return rows

    raw = json.loads(path.read_text())
    return [{"id": k, key_name: k, **v} for k, v in raw.items()]


def load(dataset: str) -> list[dict]:
    """All records in a dataset, as a fresh list of copies."""
    if dataset not in DATASETS:
        raise ValueError(
            f"unknown dataset {dataset!r}; choose one of {', '.join(DATASETS)}")
    if dataset not in _cache:
        _cache[dataset] = _read(dataset)
    return deepcopy(_cache[dataset])


def get(dataset: str, record_id: str) -> dict | None:
    """One record by id, or None. Ids are matched case-insensitively so
    'cs-8312' and 'CS-8312' both resolve — the model is not consistent about it."""
    wanted = (record_id or "").strip().upper()
    for record in load(dataset):
        if str(record["id"]).upper() == wanted:
            return record
    return None


def field(record: dict, path: str) -> Any:
    """Read a field, supporting dotted paths into nested event metadata."""
    cur: Any = record
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def facts() -> dict:
    """The ground-truth aggregates written by scripts/generate_world.py.

    Used by the test suite to assert the aggregation layer agrees with the
    generator. Never read by the running system — the copilot computes its own
    answers from the records.
    """
    return json.loads((DATA_DIR / "generated_facts.json").read_text())
