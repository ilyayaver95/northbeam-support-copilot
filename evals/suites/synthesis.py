"""synthesis — combine facts that live in two or more documents.

Authoring rule: no single document answers the question. Each case needs at
least two facts from at least two files, and `cites_any` groups require evidence
that both were actually consulted rather than one being guessed from context.

This is where adaptive retrieval earns its place. A fixed top-1 fetch answers
half of each of these and sounds confident doing it.
"""
from __future__ import annotations

from ..grader import Case

CASES: list[Case] = [

    Case(
        id="synthesis_001",
        category="synthesis",
        question=(
            "A site went live three weeks ago on the Standard plan. Their main unit just "
            "died completely. How fast do we owe them a response, and can they get a "
            "replacement part shipped before we've had the old one back?"
        ),
        expect_declined=False,
        contains_any=[
            ["4 hour", "4-hour", "four hour"],
            ["advance replacement", "no charge", "free", "without charge"],
        ],
        cites_any=[["service_levels", "onboarding_and_commissioning"], ["parts_and_rma"]],
        notes=(
            "Standard critical is 8h, but burn-in bumps it one band to 4h; and burn-in "
            "also gives free advance replacement, which Standard would otherwise only "
            "get on a critical case at 15% of list. Needs service_levels + "
            "onboarding_and_commissioning + parts_and_rma."
        ),
    ),

    Case(
        id="synthesis_002",
        category="synthesis",
        question=(
            "If a unit is sat out of service because nobody's calibrated it in months, "
            "does that hurt the operator's availability number, and what does it do to "
            "where they sit on the bands?"
        ),
        expect_declined=False,
        contains_any=[
            ["not excluded", "counts against", "does count", "is counted", "against the operator"],
        ],
        must_not_contain=["excluded from availability", "does not count against"],
        cites_any=[["maintenance_and_calibration"], ["service_levels"]],
        notes=(
            "Overdue-calibration downtime is explicitly NOT excluded (maintenance doc), "
            "so it pushes the 30-day figure down through the bands in service_levels."
        ),
    ),

    Case(
        id="synthesis_003",
        category="synthesis",
        question=(
            "Someone's running really old firmware and something breaks. Are we still on "
            "the hook for the availability commitment, and is the part covered?"
        ),
        expect_declined=False,
        contains_any=[
            ["outside", "not covered", "no longer", "unsupported", "does not apply", "excluded"],
        ],
        cites_any=[["maintenance_and_calibration"], ["parts_and_rma"]],
        notes=(
            "Unsupported firmware puts faults outside the availability commitment "
            "(maintenance doc) AND voids warranty on that fault (parts doc). Both halves."
        ),
    ),

    Case(
        id="synthesis_004",
        category="synthesis",
        question=(
            "We blew a response target on a Mission site. Walk me through what happens "
            "next on our side and what they're entitled to ask for."
        ),
        expect_declined=False,
        contains_any=[
            ["escalat", "regional service manager"],
            ["credit", "service credit"],
        ],
        cites_any=[["fault_handling"], ["service_levels"]],
        notes=(
            "fault_handling gives the automatic escalation to the regional service "
            "manager and the one-business-day notification; service_levels gives the "
            "credit tiers and that the operator has to request them in the portal."
        ),
    ),

    Case(
        id="synthesis_005",
        category="synthesis",
        question=(
            "A brand-new site just passed acceptance. What's different about how we treat "
            "them for the next few months, and when exactly does that stop?"
        ),
        expect_declined=False,
        contains_any=[
            ["90 day", "90-day", "ninety day"],
            ["enhanced response", "one band", "spares deposit", "10%"],
        ],
        cites_any=[["onboarding_and_commissioning", "service_levels"]],
        notes=(
            "Burn-in is described in both onboarding_and_commissioning and "
            "service_levels — either citation is fine, but the answer needs both the "
            "duration and at least one of the four things it changes."
        ),
    ),

    Case(
        id="synthesis_006",
        category="synthesis",
        question=(
            "Same fault code keeps coming back on one unit. At what point do we stop "
            "swapping parts, and does that change the severity we're working to?"
        ),
        expect_declined=False,
        contains_any=[
            ["three", "3 "],
            ["engineering", "diagnostic visit", "full diagnostic"],
        ],
        cites_any=[["fault_handling"]],
        notes=(
            "Three cases, same code, same unit, inside 90 days = recurring fault: goes to "
            "engineering for a full diagnostic visit REGARDLESS of individual severity."
        ),
    ),

    Case(
        id="synthesis_007",
        category="synthesis",
        question=(
            "Their engineer wants to pull last year's availability figures out of the API "
            "to put in a board report. Can they, and what can they get instead?"
        ),
        expect_declined=False,
        contains_any=[
            ["30-day", "30 day", "current", "only the current"],
        ],
        must_not_contain=["historical availability is available", "you can retrieve historical"],
        cites_any=[["platform_api"], ["service_levels", "support_scope_faq"]],
        notes=(
            "platform_api says there is no historical endpoint; service_levels and "
            "support_scope_faq say only the current 30-day figure is retained. Answerable "
            "(not a decline) — the honest answer is that it does not exist."
        ),
    ),

    Case(
        id="synthesis_008",
        category="synthesis",
        question=(
            "Storm took out a radome overnight. Does that count against their numbers, and "
            "who pays for the panel?"
        ),
        expect_declined=False,
        contains_any=[
            ["force majeure", "excluded", "does not count", "not count against"],
        ],
        contains_all=[],
        cites_any=[["service_levels"], ["parts_and_rma"]],
        notes=(
            "service_levels excludes force majeure and storm damage from availability; "
            "parts_and_rma excludes storm damage from warranty, so the operator pays. "
            "The two halves point opposite ways, which is the test."
        ),
    ),
]
