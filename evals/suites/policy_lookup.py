"""policy_lookup — read one fact off the policy corpus.

Authoring rule: the question is phrased the way a support engineer would ask it,
NOT the way the document words it. "How long till they have to answer" rather
than "what is the response target". That gap is the point — it is what separates
real retrieval from keyword matching, and it is what the held-out paraphrases
would hit hardest.

Every case checks the fact AND the citation. Getting the number right while
citing nothing is not a pass; an answer a support engineer cannot verify is not
finished work.
"""
from __future__ import annotations

from ..grader import Case

CASES: list[Case] = [

    Case(
        id="policy_001",
        category="policy_lookup",
        question="Something's completely down at a Mission-plan site. How fast do we have to be on it?",
        expect_declined=False,
        contains_any=[["1 hour", "one hour", "1-hour"]],
        cites_any=[["service_levels"]],
        notes="Mission + critical = 1 hour. Question never uses the words 'critical' or 'response target'.",
    ),

    Case(
        id="policy_002",
        category="policy_lookup",
        question="At what point does a site's availability start getting it flagged for review?",
        expect_declined=False,
        contains_any=[["99.5", "99.5%"]],
        cites_any=[["service_levels"]],
        notes="Service review band opens at 99.5% and runs down to 99.0%.",
    ),

    Case(
        id="policy_003",
        category="policy_lookup",
        question="How long do we give a customer to send the broken part back after we've shipped them a replacement?",
        expect_declined=False,
        contains_any=[["21 day", "21-day", "twenty-one day"]],
        cites_any=[["parts_and_rma"]],
        notes="21 days for the advance-replacement return. Phrased as an ops question, not the doc's wording.",
    ),

    Case(
        id="policy_004",
        category="policy_lookup",
        question="A weather radar — how often does it need the engineer out to recalibrate it?",
        expect_declined=False,
        contains_any=[["6 month", "six month", "6-month"]],
        cites_any=[["maintenance_and_calibration"]],
        notes="NB-410 C-band weather doppler is on a 6-month interval — every other model is 12.",
    ),

    Case(
        id="policy_005",
        category="policy_lookup",
        question="How much notice do we need before someone can take a unit down for planned work?",
        expect_declined=False,
        contains_any=[["5 business day", "five business day"]],
        cites_any=[["maintenance_and_calibration"]],
        notes="Maintenance windows agreed at least 5 business days ahead.",
    ),

    Case(
        id="policy_006",
        category="policy_lookup",
        question="What header do I tell them to check when they're verifying our webhook calls are genuine?",
        expect_declined=False,
        contains_any=[["x-northbeam-signature"]],
        cites_any=[["platform_api"]],
        notes="Webhook signature header. A lexical-gap case: 'genuine' vs 'HMAC signature'.",
    ),

    Case(
        id="policy_007",
        category="policy_lookup",
        question="If they retry the same case creation twice by accident, how long before we'd actually make a duplicate?",
        expect_declined=False,
        contains_any=[["24 hour", "24-hour", "twenty-four hour"]],
        cites_any=[["platform_api"]],
        notes="Idempotency-Key is remembered for 24 hours. Question never says 'idempotency'.",
    ),

    Case(
        id="policy_008",
        category="policy_lookup",
        question="How long does a brand-new unit stay covered if it fails on its own?",
        expect_declined=False,
        contains_any=[["24 month", "24-month", "two year", "2 year"]],
        cites_any=[["parts_and_rma"]],
        notes="24-month warranty from site acceptance.",
    ),

    Case(
        id="policy_009",
        category="policy_lookup",
        question="What's the most we'd ever knock off a monthly bill when we've missed our targets?",
        expect_declined=False,
        contains_any=[["20%", "20 percent"]],
        cites_any=[["service_levels"]],
        notes="Service credits capped at 20% of the monthly fee per unit per month.",
    ),

    Case(
        id="policy_010",
        category="policy_lookup",
        question="Which firmware line are we still supporting alongside the current one?",
        expect_declined=False,
        contains_any=[["4.2"]],
        cites_any=[["maintenance_and_calibration"]],
        notes="5.0.0 is stable; the 4.2.x line is in extended support for 12 months.",
    ),

    Case(
        id="policy_011",
        category="policy_lookup",
        question="How long does a survey usually take when someone new applies?",
        expect_declined=False,
        contains_any=[["10 business day", "ten business day"]],
        cites_any=[["onboarding_and_commissioning"]],
        notes="RF site survey stage is 10 business days.",
    ),

    Case(
        id="policy_012",
        category="policy_lookup",
        question="If a returned part turns out to be fine, do we charge them anything?",
        expect_declined=False,
        contains_any=[["25%", "25 percent"]],
        cites_any=[["parts_and_rma"]],
        notes="No-fault-found diagnostic fee is 25% of list price, waived if the fault recurs in 30 days.",
    ),
]
