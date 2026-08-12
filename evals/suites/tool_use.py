"""tool_use — call the right tool with the right id.

Authoring rule: grade the CALL, not the prose. These cases exist because a
system can produce a plausible sentence about a unit without ever having looked
at it, and only the executed tool list can tell the difference.

`tool_calls` on the Answer is overwritten by the loop with what actually ran, so
a model claiming a lookup it never made cannot pass these.
"""
from __future__ import annotations

from ..grader import Case, ExpectedTool as Calls

CASES: list[Case] = [

    Case(
        id="tool_use_001",
        category="tool_use",
        question="Pull up case CS-8310 — I need the fault code and when the response is due.",
        expect_declined=False,
        calls_tools=[Calls("get_case", {"case_id": "CS-8310"})],
        contains_any=[["rx-noise-high"], ["2026-09-16", "09-16", "16 september", "september 16"]],
        notes="Direct case read by id.",
    ),

    Case(
        id="tool_use_002",
        category="tool_use",
        question="What's the status and firmware on unit RU-4118?",
        expect_declined=False,
        calls_tools=[Calls("get_unit", {"unit_id": "RU-4118"})],
        contains_any=[["degraded"]],
        notes="Direct unit read by id. RU-4118 is the degraded main mast at Cape Solvang.",
    ),

    Case(
        id="tool_use_003",
        category="tool_use",
        question="List every unit installed for OP-2742.",
        expect_declined=False,
        calls_tools=[Calls("list_units", {"operator_id": "OP-2742"})],
        notes="Collection read scoped to one operator.",
    ),

    Case(
        id="tool_use_004",
        category="tool_use",
        question="Show me all the service cases on OP-2742's account.",
        expect_declined=False,
        calls_tools=[Calls("list_cases", {"operator_id": "OP-2742"})],
        contains_any=[["cs-8310"], ["cs-8312"]],
        notes="OP-2742 holds both canonical cases.",
    ),

    Case(
        id="tool_use_005",
        category="tool_use",
        question="What plan and account status is OP-2741 on?",
        expect_declined=False,
        calls_tools=[Calls("get_operator", {"operator_id": "OP-2741"})],
        contains_any=[["priority"]],
        notes="Operator profile read by id.",
    ),

    Case(
        id="tool_use_006",
        category="tool_use",
        question="Show me OP-2743's event log from 2026-09-04 onwards.",
        expect_declined=False,
        calls_tools=[Calls("read_event_log", {"operator_id": "OP-2743"})],
        contains_any=[["dispatch", "permit", "access"]],
        notes="Event log read with a since filter; surfaces the failed dispatch on 05-22.",
    ),

    Case(
        id="tool_use_007",
        category="tool_use",
        question="Open ticket TKT-3108 and tell me what it says.",
        expect_declined=False,
        calls_tools=[Calls("get_ticket", {"ticket_id": "TKT-3108"})],
        contains_any=[["cs-8312"], ["engineer", "assigned", "closed"]],
        notes="Ticket body read by id — the stale ticket behind the CS-8312 trap.",
    ),

    Case(
        id="tool_use_008",
        category="tool_use",
        question="What support tickets do we have on file for OP-2740?",
        expect_declined=False,
        calls_tools=[Calls("list_tickets", {"operator_id": "OP-2740"})],
        notes="Ticket metadata list scoped to one operator.",
    ),

    Case(
        id="tool_use_009",
        category="tool_use",
        question="Cape Solvang Port Authority — what's their current availability figure?",
        expect_declined=False,
        calls_tools=[Calls("find_operator")],
        contains_any=[["99.3", "0.9931", "99.31"]],
        notes=(
            "Name, not id. Must resolve through find_operator before it can read "
            "anything — the case that fails if name resolution is skipped."
        ),
    ),

    Case(
        id="tool_use_010",
        category="tool_use",
        question="How many units are sitting offline across the whole estate right now?",
        expect_declined=False,
        calls_tools=[Calls("aggregate_records", {"dataset": "units"})],
        forbidden_tools=["get_unit"],
        notes=(
            "A fleet-wide count MUST go through the calculation layer. Reaching for "
            "get_unit here means it is trying to count by hand, which is the exact "
            "failure the aggregation tool exists to remove."
        ),
    ),

    Case(
        id="tool_use_011",
        category="tool_use",
        question="What's 15% of a 2,280,000 cent annual fee, in whole cents?",
        expect_declined=False,
        calls_tools=[Calls("compute")],
        contains_any=[["342000", "342,000"]],
        notes="Arithmetic goes through compute, never the model's head.",
    ),

    Case(
        id="tool_use_012",
        category="tool_use",
        question="What does our policy say about who pays when a fault turns out to be a site power problem?",
        expect_declined=False,
        calls_tools=[Calls("search_policies")],
        cites_any=[["maintenance_and_calibration"]],
        notes="Policy question routes to retrieval, not to the record tools.",
    ),
]
