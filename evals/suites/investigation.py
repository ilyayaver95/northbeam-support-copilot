"""investigation — pull records and reach the right conclusion.

Authoring rule: every case here has a shallow reading that is WRONG. Passing
means both calling the right tools and committing to the correct conclusion, so
each case names the wrong answer in `must_not_contain`. Hedging fails too — the
grader's hedge check applies, so "it's hard to say" scores zero even when it
avoids saying anything false.

The traps, all from scripts/generate_world.py:

  CS-8312     due 2026-09-11, today 2026-09-14, no response logged -> BREACHED.
             TKT-3108 was closed 05-18 saying "handled", which is the bait.
  OP-2742    99.31% is the SERVICE REVIEW band, not contract review.
  OP-2743    4-hour response because of the 90-day burn-in, not because they
             are a problem account.
  OP-2745    Verdemar Offshore was declined at survey and is not an operator.
  RU-49999   does not exist.

The last five cases are aggregation, and their expected values come from
data/generated_facts.json. Regenerate the data rather than editing them.
"""
from __future__ import annotations

from ..grader import Case, ExpectedTool as Calls

CASES: list[Case] = [

    Case(
        id="investigation_001",
        category="investigation",
        question=(
            "The operator's telling me case CS-8312 is handled. Is it actually still "
            "inside the response window or did we miss it?"
        ),
        expect_declined=False,
        calls_tools=[Calls("get_case", {"case_id": "CS-8312"})],
        contains_any=[["breach", "missed", "passed", "expired", "overdue",
                       "outside", "05-22"]],
        must_not_contain=["still inside", "still have time", "on track", "not yet due",
                          "within the window", "still actionable"],
        notes=(
            "THE headline trap. Due 05-22, today is 05-25, response_logged is false. "
            "TKT-3108 says handled and was closed before the window expired — the case "
            "record is the authority."
        ),
    ),

    Case(
        id="investigation_002",
        category="investigation",
        question="Is Cape Solvang about to go into contract review over their availability?",
        expect_declined=False,
        contains_any=[["service review", "99.5", "no", "not"]],
        must_not_contain=["contract review is triggered", "will go into contract review",
                          "below 99.0", "yes, they are in contract review"],
        notes=(
            "False-alarm trap. 99.31% is in the 99.0-99.5% service review band. Contract "
            "review needs below 99.0%. Panicking here is the failure."
        ),
    ),

    Case(
        id="investigation_003",
        category="investigation",
        question="Pull up Verdemar Offshore and tell me what support plan they're on.",
        expect_declined=False,
        contains_any=[["not an operator", "declined", "not on the platform", "no account",
                       "does not exist", "doesn't exist", "no record", "was rejected",
                       "never became"]],
        must_not_contain=["standard plan", "priority plan", "mission plan",
                          "they are on the", "their plan is"],
        notes=(
            "Hallucination trap. OP-2745 failed the RF site survey and is not in "
            "operators.json. Inventing a plan is the failure; saying they are not an "
            "operator is the correct ANSWER, not a decline."
        ),
    ),

    Case(
        id="investigation_004",
        category="investigation",
        question="Why is Kettleworth on a 4-hour response when they're only on Standard?",
        expect_declined=False,
        contains_any=[["burn-in", "burn in", "90 day", "90-day", "newly commissioned",
                       "new site", "commissioning"]],
        must_not_contain=["because they are high risk", "high-risk", "poor availability",
                          "because of their availability", "they were upgraded",
                          "they pay for", "problem account"],
        notes=(
            "OP-2743 onboarded 2026-06-30 — 76 days ago, inside the 90-day burn-in, "
            "which bumps response one band. Nothing to do with standing or risk."
        ),
    ),

    Case(
        id="investigation_005",
        category="investigation",
        question="Has Cape Solvang got anything that's already blown its response deadline?",
        expect_declined=False,
        calls_tools=[Calls("list_cases", {"operator_id": "OP-2742"})],
        contains_any=[["cs-8312"], ["yes", "breach", "missed", "past"]],
        must_not_contain=["nothing is overdue", "no cases are past", "all within",
                          "nothing has been missed"],
        notes="Requires listing cases and comparing each sla_response_due against today.",
    ),

    Case(
        id="investigation_006",
        category="investigation",
        question="What's the status of unit RU-49999?",
        expect_declined=False,
        calls_tools=[Calls("get_unit", {"unit_id": "RU-49999"})],
        contains_any=[["not found", "does not exist", "doesn't exist", "no such",
                       "no record", "no unit"]],
        notes="Not-found handling. Must not fabricate a status. Answered, not declined.",
    ),

    Case(
        id="investigation_007",
        category="investigation",
        question="We can't seem to get an engineer out to Kettleworth. Find out what's going on.",
        expect_declined=False,
        calls_tools=[Calls("read_event_log", {"operator_id": "OP-2743"})],
        contains_any=[["permit", "access", "expired"]],
        notes="OP-2743 dispatch_failed on 2026-09-11: site access permit expired, retry pending.",
    ),

    Case(
        id="investigation_008",
        category="investigation",
        question=(
            "Of Cape Solvang's open cases, which one still needs us this week and which "
            "one have we already lost?"
        ),
        expect_declined=False,
        calls_tools=[Calls("list_cases", {"operator_id": "OP-2742"})],
        contains_all=["cs-8312"],
        contains_any=[["cs-8310"], ["breach", "missed", "blown", "past due"]],
        must_not_contain=["both are still", "nothing has been missed", "all within window"],
        notes="CS-8310 due 05-27 is live; CS-8312 due 05-22 is gone. Per-case date reasoning.",
    ),

    Case(
        id="investigation_009",
        category="investigation",
        question="When did Cape Solvang's availability first trip a warning, and at what figure?",
        expect_declined=False,
        contains_any=[["99.31", "0.9931", "99.3"], ["2026-09-08", "09-08", "8 september", "september 8"]],
        notes="availability_warning event for OP-2742 logged 2026-09-08 at 0.9931.",
    ),

    Case(
        id="investigation_010",
        category="investigation",
        question="Walk me through everything that's happened on Cape Solvang since mid-May and tell me what still needs doing.",
        expect_declined=False,
        calls_tools=[Calls("read_event_log", {"operator_id": "OP-2742"})],
        contains_any=[["cs-8312", "case", "warning", "availability", "breach"]],
        must_not_contain=["nothing needs", "no follow-up", "everything looks fine",
                          "nothing outstanding"],
        notes=(
            "Open-ended. The log since 05-15 has case_opened and availability_warning; "
            "CS-8312 is the outstanding item."
        ),
    ),

    # ---- aggregation: expected values from data/generated_facts.json ----------

    Case(
        id="investigation_011",
        category="investigation",
        question="Which operator has had the most failed engineer dispatches this month, and how many?",
        expect_declined=False,
        contains_any=[["op-2751", "ridgeway & holt", "ridgeway and holt"], ["4", "four"]],
        notes=(
            "facts.most_failed_dispatches: OP-2751 with 4. Runners-up have 1 each, and "
            "OP-2759's was retried successfully — the red herring. Needs a grouped sweep, "
            "not 33 separate log reads."
        ),
    ),

    Case(
        id="investigation_012",
        category="investigation",
        question=(
            "How many service cases are still open, still inside their window, and due on "
            "or before 2026-09-30?"
        ),
        expect_declined=False,
        contains_any=[["10", "ten"]],
        notes=(
            "facts.open_cases_due_by_month_end: exactly 10. Precisely worded on purpose — "
            "excludes cases with a response already logged AND the breached CS-8312."
        ),
    ),

    Case(
        id="investigation_013",
        category="investigation",
        question="Which operators are at or below the 99.5% availability threshold right now?",
        expect_declined=False,
        contains_all=["op-2742"],
        contains_any=[["op-2769", "aiguille"]],
        must_not_contain=["op-2764", "northreach"],
        notes=(
            "facts.operators_at_or_below_995: exactly OP-2742 (0.9931) and OP-2769 "
            "(0.9884). OP-2764 (Northreach Ice Survey) at 0.9952 is the deliberate "
            "near-miss and must NOT appear."
        ),
    ),

    Case(
        id="investigation_014",
        category="investigation",
        question="Across every operator, which open case has the biggest parts cost, and what is it?",
        expect_declined=False,
        contains_all=["cs-8321"],
        contains_any=[["4,026", "4026", "402,600", "402600"]],
        notes=(
            "facts.largest_open_case: CS-8321 at 402600 cents = $4,026.00. Bigger than the "
            "canonical CS-8312 at $1,439.00 — a system that only knows the hand-written "
            "cases gets this wrong."
        ),
    ),

    Case(
        id="investigation_015",
        category="investigation",
        question="How many service cases does Cape Solvang have on file?",
        expect_declined=False,
        calls_tools=[Calls("list_cases", {"operator_id": "OP-2742"})],
        contains_any=[["2 ", "two"]],
        must_not_contain=["3 cases", "three cases", "1 case", "one case"],
        notes="facts.case_counts_by_operator: OP-2742 has exactly 2 (CS-8310 and CS-8312).",
    ),
]
