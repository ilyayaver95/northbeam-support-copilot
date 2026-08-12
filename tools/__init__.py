"""tools/ — everything the copilot can actually do.

Three layers, and the split is deliberate:

  records.py    read ONE thing, or the things belonging to ONE operator.
                Narrow returns so a citation maps to a real record.

  aggregate.py  count / total / rank across a whole dataset, plus compute.py for
  compute.py    the derived arithmetic. This is the calculation layer: the model
                chooses what to compute, Python computes it, so no number in an
                answer was ever produced by a language model doing sums.

  retrieval.py  hybrid keyword + semantic search over the policy corpus.

All of them are pure reads. There is no tool that changes anything, which is not
an oversight — it is the reason `refusal.py` can treat "restart that unit" as a
capability fact rather than a judgment call.
"""
from .records import (
    find_operator, get_operator, get_unit, list_units,
    get_case, list_cases, list_tickets, get_ticket, read_event_log,
)
from .aggregate import aggregate_records
from .compute import compute
from .retrieval import search_policies

__all__ = [
    "find_operator",
    "get_operator",
    "get_unit",
    "list_units",
    "get_case",
    "list_cases",
    "list_tickets",
    "get_ticket",
    "read_event_log",
    "aggregate_records",
    "compute",
    "search_policies",
]
