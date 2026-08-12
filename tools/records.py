"""records.py — the read tools over structured data.

Each one answers a question about ONE thing, or lists the things belonging to one
operator. Anything that needs a count, a total, or a ranking across the whole
fleet goes to `aggregate.py` instead — see the note at the bottom of this file.

Every tool returns either the data or `{"error": ...}`. None of them raise, and
none of them guess: a missing record is reported as missing, because "there is no
such unit" is a legitimate answer that the copilot must be able to give.
"""
from __future__ import annotations

import difflib
from pathlib import Path

from . import store

TICKETS_DIR = store.DATA_DIR / "tickets"


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------


def find_operator(query: str) -> dict:
    """Resolve an operator name or id to a record.

    This is the entry point for any question that names an operator in prose
    ("Cape Solvang", "the Kettleworth site") rather than by id. Matching is
    case-insensitive, tolerates partial names, and falls back to fuzzy matching
    on close spellings.

    Args:
        query: an operator id ("OP-2742") or any part of the name
               ("cape solvang", "Kettleworth").

    Returns:
        {"match": {...}} for a single confident hit,
        {"candidates": [...]} when several operators match,
        {"error": "..."} when nothing matches — which is a real answer: the
        organisation is not an operator on the platform.
    """
    q = (query or "").strip().lower()
    if not q:
        return {"error": "find_operator needs a name or id to look for"}

    operators = store.load("operators")

    for op in operators:
        if op["id"].lower() == q:
            return {"match": op}

    exact = [op for op in operators if op["name"].lower() == q]
    if exact:
        return {"match": exact[0]}

    partial = [op for op in operators if q in op["name"].lower()]
    if len(partial) == 1:
        return {"match": partial[0]}
    if partial:
        return {"candidates": [{"operator_id": o["id"], "name": o["name"]} for o in partial]}

    names = {op["name"].lower(): op for op in operators}
    close = difflib.get_close_matches(q, list(names), n=3, cutoff=0.75)
    if len(close) == 1:
        return {"match": names[close[0]]}
    if close:
        return {"candidates": [{"operator_id": names[c]["id"], "name": names[c]["name"]}
                               for c in close]}

    return {"error": f"no operator matching {query!r} — no such operator is on the platform"}


def get_operator(operator_id: str) -> dict:
    """One operator's profile: plan, status, availability, flags, onboarding date.

    Args:
        operator_id: e.g. "OP-2742".

    Returns:
        The operator record, or {"error": "not found"} — which is the correct
        answer for an applicant that was declined and never became an operator.
    """
    record = store.get("operators", operator_id)
    if record is None:
        return {"error": f"operator {operator_id} not found"}
    return record


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


def get_unit(unit_id: str) -> dict:
    """One radar unit: model, band, site, status, firmware, calibration, downtime.

    Args:
        unit_id: e.g. "RU-4118".
    """
    record = store.get("units", unit_id)
    if record is None:
        return {"error": f"unit {unit_id} not found"}
    return record


def list_units(operator_id: str) -> list[dict] | dict:
    """Every unit installed for one operator.

    Args:
        operator_id: e.g. "OP-2742".

    Returns:
        A list of unit records, or [] if the operator has none.
    """
    return [u for u in store.load("units") if u["operator_id"] == operator_id]


# ---------------------------------------------------------------------------
# Service cases
# ---------------------------------------------------------------------------


def get_case(case_id: str) -> dict:
    """One service case: severity, fault code, when it opened, when the SLA
    response is due, and whether a response has been logged.

    The case record — not a support ticket — is the authority on where a fault
    stands. Compare `sla_response_due` against today to judge whether the window
    has been missed.

    Args:
        case_id: e.g. "CS-8312".
    """
    record = store.get("cases", case_id)
    if record is None:
        return {"error": f"case {case_id} not found"}
    return record


def list_cases(operator_id: str) -> list[dict]:
    """Every service case for one operator, open or closed.

    Args:
        operator_id: e.g. "OP-2742".
    """
    return [c for c in store.load("cases") if c["operator_id"] == operator_id]


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------


def list_tickets(operator_id: str) -> list[dict]:
    """Past support tickets for one operator — metadata only, newest first.

    Args:
        operator_id: e.g. "OP-2742".
    """
    rows = [t for t in store.load("tickets") if t["operator_id"] == operator_id]
    rows.sort(key=lambda t: t.get("opened_on", ""), reverse=True)
    return [{k: v for k, v in t.items() if k != "file"} for t in rows]


def get_ticket(ticket_id: str) -> dict:
    """The full text of one past support ticket.

    Tickets are correspondence, not the system of record. Where a ticket and a
    case record disagree, the case record wins — tickets are routinely closed
    before the underlying case is resolved.

    Args:
        ticket_id: e.g. "TKT-3108".
    """
    meta = store.get("tickets", ticket_id)
    if meta is None:
        return {"error": f"ticket {ticket_id} not found"}
    path = Path(TICKETS_DIR) / meta["file"]
    if not path.exists():
        return {"error": f"ticket {ticket_id} has no body on file"}
    return {k: v for k, v in meta.items() if k != "file"} | {"body": path.read_text()}


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


def read_event_log(operator_id: str, since: str | None = None,
                   event_type: str | None = None) -> list[dict]:
    """Event-log entries for ONE operator, oldest first.

    Event types include: unit_alarm, unit_offline, unit_restored, case_opened,
    availability_warning, calibration_completed, firmware_updated,
    field_visit_completed, dispatch_failed, part_shipped, onboarding_declined.

    Deliberately scoped to a single operator. Cross-operator questions ("which
    operator had the most failed dispatches") must go through
    `aggregate_records`, which applies the same internal-triage boundary in one
    auditable place rather than being assembled by hand from many calls.

    Args:
        operator_id: e.g. "OP-2742".
        since: optional ISO date, YYYY-MM-DD, inclusive.
        event_type: optional exact event type filter.
    """
    events = [e for e in store.load("events") if e.get("operator_id") == operator_id]
    if since:
        events = [e for e in events if e["date"] >= since]
    if event_type:
        events = [e for e in events if e["event_type"] == event_type]
    events.sort(key=lambda e: e["timestamp"])
    return events
