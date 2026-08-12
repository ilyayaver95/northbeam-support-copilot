"""toolkit.py — what the model is told it can do, and what actually runs.

Two things live here and they must not drift apart:

    REGISTRY   name -> the Python callable the loop invokes as fn(**args)
    SCHEMAS    name -> the JSON schema the model routes on

`tests/test_contracts.py` asserts they stay in sync — that every registered tool
has a schema, every schema has a tool, every declared property is a real
parameter, and every parameter without a default is marked required. Those are
the failures that don't raise until the model has already hallucinated around
them.

Tool descriptions are prompt content, not documentation. They are the only thing
the model sees when choosing, so they say when to reach for a tool, not just
what it returns.
"""
from __future__ import annotations

from tools import (
    aggregate_records, compute, find_operator, get_case, get_operator,
    get_ticket, get_unit, list_cases, list_tickets, list_units,
    read_event_log, search_policies,
)

REGISTRY = {
    "find_operator": find_operator,
    "get_operator": get_operator,
    "get_unit": get_unit,
    "list_units": list_units,
    "get_case": get_case,
    "list_cases": list_cases,
    "list_tickets": list_tickets,
    "get_ticket": get_ticket,
    "read_event_log": read_event_log,
    "search_policies": search_policies,
    "aggregate_records": aggregate_records,
    "compute": compute,
}

# Tools whose output is computed rather than read off a record. Surfaced in the
# UI and in the trace, because "this number came out of Python" is the single
# most useful thing to know about a numeric answer.
COMPUTED_TOOLS = {"aggregate_records", "compute"}


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


TOOL_SCHEMAS = [

    # ---- resolution -------------------------------------------------------

    _tool("find_operator",
          "Resolve an operator named in prose ('Cape Solvang', 'the Kettleworth "
          "site') to its record and id. START HERE whenever a question names an "
          "organisation rather than giving an OP- id. Returns {'match': ...} for one "
          "hit, {'candidates': [...]} when several match, or an error when nothing "
          "matches — and nothing matching is a real answer: they are not an operator "
          "on the platform.",
          {"query": {"type": "string",
                     "description": "Operator name, part of a name, or an id like 'OP-2742'."}},
          ["query"]),

    # ---- single records ---------------------------------------------------

    _tool("get_operator",
          "One operator's profile: support plan (Standard/Priority/Mission), account "
          "status, 30-day availability (a FRACTION — 0.9931 is 99.31%), enhanced "
          "response flag, spares deposit, account flags, onboarding date. Returns an "
          "error for an id that is not an operator.",
          {"operator_id": {"type": "string", "description": "e.g. 'OP-2742'."}},
          ["operator_id"]),

    _tool("get_unit",
          "One radar unit: model (NB-410/620/870/880), band, site, commissioning "
          "date, status (operational/degraded/offline/decommissioned), firmware, last "
          "calibration date, rolling 30-day downtime minutes, annual service fee.",
          {"unit_id": {"type": "string", "description": "e.g. 'RU-4118'."}},
          ["unit_id"]),

    _tool("list_units",
          "Every radar unit installed for ONE operator, with each unit's status, model "
          "and downtime. Use when a question is about an operator's estate as a whole. "
          "For a count or total across ALL operators, use aggregate_records instead.",
          {"operator_id": {"type": "string", "description": "e.g. 'OP-2742'."}},
          ["operator_id"]),

    _tool("get_case",
          "One service case: severity, fault code, opened_at, sla_response_due, and "
          "response_logged. To judge whether a response window has been missed, "
          "compare sla_response_due against today and check response_logged — the "
          "CASE RECORD is the authority, not a support ticket.",
          {"case_id": {"type": "string", "description": "e.g. 'CS-8312'."}},
          ["case_id"]),

    _tool("list_cases",
          "Every service case for ONE operator, open and closed, each with its severity "
          "and sla_response_due. Use to find which of an operator's cases are still "
          "inside their window and which have been missed. For counts across ALL "
          "operators, use aggregate_records instead.",
          {"operator_id": {"type": "string", "description": "e.g. 'OP-2742'."}},
          ["operator_id"]),

    _tool("list_tickets",
          "Past support tickets for one operator — metadata only, newest first.",
          {"operator_id": {"type": "string", "description": "e.g. 'OP-2742'."}},
          ["operator_id"]),

    _tool("get_ticket",
          "The full text of one past support ticket. Tickets are correspondence and "
          "are often closed before the underlying case is resolved — where a ticket "
          "and a case record disagree, trust the case record.",
          {"ticket_id": {"type": "string", "description": "e.g. 'TKT-3108'."}},
          ["ticket_id"]),

    _tool("read_event_log",
          "Event-log entries for ONE operator, oldest first. Types include "
          "unit_alarm, unit_offline, unit_restored, case_opened, "
          "availability_warning, calibration_completed, firmware_updated, "
          "field_visit_completed, dispatch_failed, part_shipped, "
          "onboarding_declined. Scoped to one operator by design — for "
          "cross-operator questions use aggregate_records.",
          {
              "operator_id": {"type": "string", "description": "e.g. 'OP-2742'."},
              "since": {"type": "string",
                        "description": "Optional ISO date YYYY-MM-DD, inclusive."},
              "event_type": {"type": "string",
                             "description": "Optional exact event type, e.g. 'dispatch_failed'."},
          },
          ["operator_id"]),

    # ---- retrieval --------------------------------------------------------

    _tool("search_policies",
          "Hybrid keyword + semantic search over the policy documents. Use for "
          "service levels and response targets, availability bands, service credits, "
          "fault severity and escalation, calibration and maintenance windows, "
          "firmware support, spare parts, RMA and warranty, onboarding and "
          "commissioning, the portal API, and what Northbeam does and does not "
          "store. Cite the doc_id you rely on.",
          {
              "query": {"type": "string",
                        "description": "Plain-language query, e.g. 'critical fault response target'."},
              "top_k": {"type": "integer",
                        "description": "Optional lower bound on documents returned."},
          },
          ["query"]),

    # ---- calculation layer ------------------------------------------------
    # Everything above returns ONE record or one operator's records. Anything
    # needing a count, a total, or a ranking comes through here so the
    # arithmetic happens in Python instead of in the model's head.

    _tool("aggregate_records",
          "Count, total, average, rank or filter across a WHOLE dataset. Use this for "
          "every 'how many', 'total', 'largest', 'most', 'which ones are above/below "
          "X' question — never add records up yourself. "
          "Datasets and their fields: "
          "'operators' (name, sector, support_plan, status, availability_30d as a "
          "FRACTION so 99.5% is 0.995, on_enhanced_response, spares_deposit_pct, "
          "onboarded_on, account_flags); "
          "'units' (operator_id, model, band, site, status, firmware, "
          "commissioned_on, last_calibration_on, downtime_minutes_30d, "
          "annual_service_fee_cents); "
          "'cases' (operator_id, unit_id, severity, fault_code, opened_at, "
          "sla_response_due, response_logged, parts_cost_cents, downtime_minutes); "
          "'events' (date, event_type, operator_id, unit_id, metadata); "
          "'tickets' (operator_id, subject, status, opened_on, closed_on). "
          "Returns the value, the ids of the records behind it, and a 'computation' "
          "string describing exactly what ran. Cite those record ids in your answer. "
          "Filter fields must be real field names from the list above — an unknown "
          "field returns an error listing the valid ones, so read the error and retry "
          "rather than reporting zero.",
          {
              "dataset": {
                  "type": "string",
                  "enum": ["operators", "units", "cases", "events", "tickets"],
                  "description": "Which dataset to compute over.",
              },
              "metric": {
                  "type": "string",
                  "enum": ["count", "sum", "avg", "min", "max", "list"],
                  "description": "count = how many; sum/avg/min/max need `field`; "
                                 "list = return the matching records.",
              },
              "field": {
                  "type": "string",
                  "description": "Numeric field for sum/avg/min/max, e.g. "
                                 "'parts_cost_cents', 'downtime_minutes_30d', "
                                 "'availability_30d'. Dotted paths reach event "
                                 "metadata, e.g. 'metadata.availability_30d'.",
              },
              "filters": {
                  "type": "array",
                  "description": "AND-ed conditions. ISO dates compare as plain "
                                 "strings, so {'field':'sla_response_due','op':'lte',"
                                 "'value':'2026-09-30'} works as written.",
                  "items": {
                      "type": "object",
                      "properties": {
                          "field": {"type": "string", "description": "Field name, e.g. 'severity'."},
                          "op": {
                              "type": "string",
                              "enum": ["eq", "ne", "gt", "gte", "lt", "lte", "in",
                                       "not_in", "contains", "starts_with", "exists"],
                              "description": "Comparison operator.",
                          },
                          "value": {"description": "Value to compare against."},
                      },
                      "required": ["field", "op", "value"],
                  },
              },
              "group_by": {
                  "type": "string",
                  "description": "Field to group on before computing, e.g. "
                                 "'operator_id' or 'event_type'. Groups come back "
                                 "ranked — this is how 'which operator has the most "
                                 "X' is answered.",
              },
              "sort": {"type": "string", "enum": ["desc", "asc"],
                       "description": "Ranking direction, default 'desc'."},
              "limit": {"type": "integer",
                        "description": "Max groups or records returned, default 10."},
          },
          ["dataset", "metric"]),

    _tool("compute",
          "Evaluate an arithmetic expression exactly. Use for service credits, "
          "percentages, cents-to-currency and minutes-to-hours instead of working it "
          "out yourself, e.g. '317500 / 100' or 'round(0.9931 * 100, 2)'. Numbers and "
          "operators only — no field names or variables, substitute the real numbers "
          "first.",
          {"expression": {"type": "string",
                          "description": "Pure arithmetic, e.g. 'round(2400000 * 0.05 / 12, 2)'."}},
          ["expression"]),
]
