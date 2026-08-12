#!/usr/bin/env python3
"""generate_world.py — builds the Northbeam Radar Systems dataset.

    python scripts/generate_world.py

Deterministic: fixed seed, so the same data comes out every time and the eval
suites can assert exact numbers. Regenerate rather than hand-editing `data/` —
`generated_facts.json` holds the ground-truth aggregates the eval suites assert
against, and it is only correct if it was written by the same run that wrote
the records.

The world is built around deliberate traps — situations where the shallow read
and the correct read disagree. A copilot that skims gets them wrong:

  CS-8312  critical case whose SLA response window closed three days before
           TODAY, so it is BREACHED. Ticket TKT-3108 was closed four days
           before it expired and says "engineer assigned, all good" — trusting
           the ticket over the record is the trap.
  OP-2742  99.31% availability sits in the 99.0-99.5% SERVICE REVIEW band, not
           the sub-99.0% CONTRACT REVIEW band. Crying breach is a false alarm.
  OP-2745  Verdemar Offshore was DECLINED at site survey and is not in
           operators.json at all. Inventing a support plan for them is a
           hallucination.
  OP-2743  on 4-hour response because they are 76 days into the 90-day
           commissioning burn-in — NOT because they are a problem account.
  RU-49999 does not exist.
  OP-2764  99.52% availability: a deliberate near-miss just above the 99.5%
           threshold, so "which operators are at or below it" can be got wrong
           by one.
"""
from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 71409263
TODAY = date(2026, 9, 14)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TICKETS = DATA / "tickets"

rng = random.Random(SEED)


def iso(d: date) -> str:
    return d.isoformat()


def ago(days: int) -> str:
    """A date `days` before TODAY, as ISO. Negative days means the future."""
    return iso(TODAY - timedelta(days=days))


def _month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


# The "due by month end" questions anchor here rather than on a literal date, so
# the timeline can move without every aggregate having to be rewritten.
MONTH_END = iso(_month_end(TODAY))


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

# The five canonical operators carry the traps. Everything after OP-2745 is
# generated, so the suites also test name resolution beyond the hand-written set.
CANONICAL_OPERATORS = {
    "OP-2740": {
        "name": "Harborlight Marine Services",
        "sector": "maritime",
        "support_plan": "Standard",
        "onboarded_on": ago(1002),
        "status": "active",
        "availability_30d": 0.9987,
        "on_enhanced_response": False,
        "spares_deposit_pct": 0.0,
        "account_flags": [],
        "city": "Halifax",
        "country": "CA",
    },
    "OP-2741": {
        "name": "Stralsund Meteorological Institute",
        "sector": "meteorology",
        "support_plan": "Priority",
        "onboarded_on": ago(1246),
        "status": "active",
        "availability_30d": 0.9971,
        "on_enhanced_response": False,
        "spares_deposit_pct": 0.0,
        "account_flags": ["weekly_maintenance_window"],
        "city": "Stralsund",
        "country": "DE",
    },
    # The false-alarm trap: 99.31% is service review, NOT contract review.
    "OP-2742": {
        "name": "Cape Solvang Port Authority",
        "sector": "maritime",
        "support_plan": "Mission",
        "onboarded_on": ago(1520),
        "status": "service_review",
        "availability_30d": 0.9931,
        "on_enhanced_response": True,
        "spares_deposit_pct": 0.15,
        "account_flags": ["availability_watch", "coastal_high_clutter"],
        "city": "Cape Solvang",
        "country": "ZA",
    },
    # The burn-in trap: enhanced response because they are NEW, not troubled.
    # Onboarded 76 days ago, so still inside the 90-day window.
    "OP-2743": {
        "name": "Kettleworth Regional Airport",
        "sector": "aviation",
        "support_plan": "Standard",
        "onboarded_on": ago(76),
        "status": "active",
        "availability_30d": 0.9964,
        "on_enhanced_response": True,
        "spares_deposit_pct": 0.10,
        "account_flags": ["commissioning_burn_in"],
        "city": "Kettleworth",
        "country": "GB",
    },
    "OP-2744": {
        "name": "Tallgrass Weather Network",
        "sector": "meteorology",
        "support_plan": "Priority",
        "onboarded_on": ago(1980),
        "status": "active",
        "availability_30d": 0.9979,
        "on_enhanced_response": False,
        "spares_deposit_pct": 0.0,
        "account_flags": [],
        "city": "Wichita",
        "country": "US",
    },
    # NOTE: OP-2745 (Verdemar Offshore Systems) is intentionally ABSENT — declined
    # at site survey. It exists only in the event log and TKT-3103.
}

GENERATED_NAMES = [
    ("Fjordline Vessel Traffic", "maritime", "Bergen", "NO"),
    ("Aldergrove Approach Control", "aviation", "Aldergrove", "GB"),
    ("Sablefish Bay Harbour Trust", "maritime", "Sablefish Bay", "CA"),
    ("Monsoon Watch Authority", "meteorology", "Kochi", "IN"),
    ("Grantwood Municipal Airfield", "aviation", "Grantwood", "US"),
    ("Ridgeway & Holt Port Logistics", "maritime", "Rotterdam", "NL"),
    ("Highfell Upland Observatory", "meteorology", "Highfell", "GB"),
    ("Saltmarsh Estuary Control", "maritime", "Saltmarsh", "IE"),
    ("Pinehurst Field Operations", "aviation", "Pinehurst", "US"),
    ("Kestrel Ridge Met Station", "meteorology", "Kestrel Ridge", "NZ"),
    ("Drakensberg Air Navigation", "aviation", "Bloemfontein", "ZA"),
    ("Lantern Rock Pilotage", "maritime", "Lantern Rock", "AU"),
    ("Verano Coastal Institute", "meteorology", "Valparaiso", "CL"),
    ("Thornbury Regional Tower", "aviation", "Thornbury", "CA"),
    ("Marisol Deepwater Terminal", "maritime", "Marisol", "SG"),
    ("Brackenmoor Storm Centre", "meteorology", "Brackenmoor", "GB"),
    ("Silverkeel Shipping Lanes", "maritime", "Silverkeel", "IS"),
    ("Ashgrove Flight Information", "aviation", "Ashgrove", "AU"),
    ("Northreach Ice Survey", "meteorology", "Northreach", "NO"),
    ("Pelham Point Harbour", "maritime", "Pelham Point", "US"),
    ("Duneford Coastal Watch", "maritime", "Duneford", "NL"),
    ("Ironvale Aviation Services", "aviation", "Ironvale", "US"),
    ("Windlass Bay Authority", "maritime", "Windlass Bay", "NZ"),
    ("Aiguille Mountain Met", "meteorology", "Aiguille", "CH"),
    ("Emberton Airfield Group", "aviation", "Emberton", "GB"),
    ("Quarrystone Docks", "maritime", "Quarrystone", "PT"),
    ("Windrose Weather Bureau", "meteorology", "Windrose", "US"),
    ("Calloway Straits Control", "maritime", "Calloway Straits", "MY"),
]

PLANS = ["Standard", "Priority", "Mission"]


def build_operators() -> dict:
    operators = dict(CANONICAL_OPERATORS)

    for i, (name, sector, city, country) in enumerate(GENERATED_NAMES):
        oid = f"OP-{2746 + i}"
        availability = round(rng.uniform(0.9955, 0.9998), 4)
        operators[oid] = {
            "name": name,
            "sector": sector,
            "support_plan": rng.choice(PLANS),
            "onboarded_on": iso(TODAY - timedelta(days=rng.randint(200, 2000))),
            "status": "active",
            "availability_30d": availability,
            "on_enhanced_response": False,
            "spares_deposit_pct": 0.0,
            "account_flags": [],
            "city": city,
            "country": country,
        }

    # OP-2764 is the deliberate near-miss: just ABOVE the 99.5% threshold, so it
    # must not appear in "at or below 99.5%" answers.
    operators["OP-2764"]["availability_30d"] = 0.9952
    operators["OP-2764"]["account_flags"] = ["availability_watch"]

    # OP-2769 is genuinely below the CONTRACT REVIEW line — the only suspended one.
    operators["OP-2769"]["availability_30d"] = 0.9884
    operators["OP-2769"]["status"] = "contract_review"
    operators["OP-2769"]["on_enhanced_response"] = True
    operators["OP-2769"]["spares_deposit_pct"] = 0.20
    operators["OP-2769"]["account_flags"] = ["availability_watch", "contract_review"]

    return operators


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

MODELS = [
    ("NB-620", "X", "marine surveillance"),
    ("NB-870", "S", "primary surveillance"),
    ("NB-410", "C", "weather doppler"),
    ("NB-880", "S", "secondary surveillance"),
]

SECTOR_MODELS = {
    "maritime": ["NB-620", "NB-870"],
    "aviation": ["NB-870", "NB-880"],
    "meteorology": ["NB-410"],
}

SITE_SUFFIXES = ["Outer Approach", "North Head", "Main Mast", "West Ridge",
                 "Terminal Array", "Coastal Tower", "Ridgetop Site", "Harbour Point",
                 "Runway Array", "Backup Mast"]


def build_units(operators: dict) -> dict:
    units: dict[str, dict] = {}
    band_of = {m: b for m, b, _ in MODELS}
    oids = list(operators)
    n = 213

    for i in range(n):
        uid = f"RU-{4001 + i}"
        oid = oids[i % len(oids)]
        op = operators[oid]
        model = rng.choice(SECTOR_MODELS[op["sector"]])
        commissioned = max(
            date.fromisoformat(op["onboarded_on"]),
            TODAY - timedelta(days=rng.randint(30, 1800)),
        )
        status = rng.choices(
            ["operational", "degraded", "offline", "decommissioned"],
            weights=[84, 9, 5, 2],
        )[0]
        downtime = {
            "operational": rng.randint(0, 30),
            "degraded": rng.randint(60, 400),
            "offline": rng.randint(400, 1800),
            "decommissioned": 0,
        }[status]

        units[uid] = {
            "operator_id": oid,
            "model": model,
            "band": band_of[model],
            "site": f"{op['city']} {rng.choice(SITE_SUFFIXES)}",
            "commissioned_on": iso(commissioned),
            "status": status,
            "firmware": rng.choice(["4.1.7", "4.2.1", "4.2.3", "5.0.0"]),
            "last_calibration_on": iso(TODAY - timedelta(days=rng.randint(10, 420))),
            "downtime_minutes_30d": downtime,
            "annual_service_fee_cents": rng.choice(
                [1735000, 2280000, 3460000, 4915000, 6740000]),
        }

    # Pin the units the traps reference.
    units["RU-4118"].update({
        "operator_id": "OP-2742",
        "model": "NB-870",
        "band": "S",
        "site": "Cape Solvang Main Mast",
        "status": "degraded",
        "commissioned_on": ago(1335),
        "last_calibration_on": ago(212),
        "downtime_minutes_30d": 386,
    })
    units["RU-4004"].update({
        "operator_id": "OP-2740",
        "model": "NB-620",
        "band": "X",
        "site": "Halifax Outer Approach",
        "status": "operational",
        "downtime_minutes_30d": 12,
    })
    return units


# ---------------------------------------------------------------------------
# Service cases
# ---------------------------------------------------------------------------

FAULT_CODES = ["TX-PWR-LOW", "RX-NOISE-HIGH", "AZ-ENC-DRIFT", "PSU-FAULT",
               "WG-PRESSURE-LOW", "MTI-DEGRADED", "COMMS-LINK-DOWN", "FAN-FAIL"]

# Hand-pinned so the deadline arithmetic is exact. `response_logged=False` means
# the SLA clock is still running.
CANONICAL_CASES = {
    # Due in two days: this week, still actionable.
    "CS-8310": {"unit_id": "RU-4119", "operator_id": "OP-2742", "opened_at": ago(5),
               "severity": "major", "fault_code": "RX-NOISE-HIGH",
               "sla_response_due": ago(-2), "response_logged": False,
               "parts_cost_cents": 74300, "downtime_minutes": 265},
    # Due in five days: comfortably open. The contrast case to CS-8312.
    "CS-8311": {"unit_id": "RU-4004", "operator_id": "OP-2740", "opened_at": ago(2),
               "severity": "minor", "fault_code": "FAN-FAIL",
               "sla_response_due": ago(-5), "response_logged": False,
               "parts_cost_cents": 6250, "downtime_minutes": 52},
    # THE TRAP: the window closed three days ago -> breached. TKT-3108 says otherwise.
    "CS-8312": {"unit_id": "RU-4118", "operator_id": "OP-2742", "opened_at": ago(10),
               "severity": "critical", "fault_code": "TX-PWR-LOW",
               "sla_response_due": ago(3), "response_logged": False,
               "parts_cost_cents": 143900, "downtime_minutes": 386},
}


def build_cases(operators: dict, units: dict) -> dict:
    cases = dict(CANONICAL_CASES)
    oids = [o for o in operators if o not in ("OP-2740", "OP-2742")]

    # 15 more, CS-8313..CS-8327, spread either side of the month-end boundary.
    for i in range(15):
        cid = f"CS-{8313 + i}"
        oid = oids[(i * 3) % len(oids)]
        op_units = [u for u, v in units.items() if v["operator_id"] == oid] or ["RU-4001"]
        opened = TODAY - timedelta(days=rng.randint(1, 12))
        severity = rng.choice(["critical", "major", "minor"])
        window = {"critical": 7, "major": 10, "minor": 14}[severity]
        cases[cid] = {
            "unit_id": rng.choice(op_units),
            "operator_id": oid,
            "opened_at": iso(opened),
            "severity": severity,
            "fault_code": rng.choice(FAULT_CODES),
            "sla_response_due": iso(opened + timedelta(days=window)),
            "response_logged": rng.random() < 0.3,
            "parts_cost_cents": rng.choice([5300, 13750, 28400, 71200, 106500, 168900]),
            "downtime_minutes": rng.randint(30, 900),
        }

    # CS-8321 is the largest open case, deliberately bigger than the canonical
    # CS-8312 — a system that only knows the hand-written cases gets this wrong.
    cases["CS-8321"].update({
        "parts_cost_cents": 402600,
        "response_logged": False,
        "sla_response_due": ago(-4),
        "severity": "critical",
        "fault_code": "PSU-FAULT",
    })

    # Force exactly 10 cases that are still INSIDE their window and due on or
    # before month end, so the count is a designed fact rather than an accident
    # of the seed. CS-8312 stays outside this set: it is already breached, which
    # is the distinction the question is testing.
    target_ids = ["CS-8310", "CS-8311", "CS-8313", "CS-8315", "CS-8316",
                  "CS-8318", "CS-8319", "CS-8321", "CS-8322", "CS-8324"]
    window_start, window_end = iso(TODAY), MONTH_END

    def in_window(case: dict) -> bool:
        return window_start <= case["sla_response_due"] <= window_end

    for cid, case in cases.items():
        if cid == "CS-8312":
            continue                                    # the breached one, left alone
        if cid in target_ids:
            case["response_logged"] = False
            if not in_window(case):
                case["sla_response_due"] = ago(-5)
        elif not case["response_logged"] and case["sla_response_due"] <= window_end:
            case["response_logged"] = True              # push it out of the count

    return cases


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------

EVENT_TYPES = ["unit_alarm", "unit_offline", "unit_restored", "case_opened",
               "calibration_completed", "firmware_updated", "field_visit_completed",
               "part_shipped"]


def build_events(operators: dict, units: dict, cases: dict) -> list[dict]:
    events: list[dict] = []

    def add(day: date, hour: int, minute: int, event_type: str, operator_id: str, **extra):
        events.append({
            "timestamp": f"{iso(day)}T{hour:02d}:{minute:02d}:00Z",
            "event_type": event_type,
            "operator_id": operator_id,
            **extra,
        })

    # --- background traffic ---
    oids = list(operators)
    for _ in range(215):
        oid = rng.choice(oids)
        op_units = [u for u, v in units.items() if v["operator_id"] == oid]
        day = TODAY - timedelta(days=rng.randint(0, 30))
        add(day, rng.randint(0, 23), rng.choice([0, 15, 30, 45]),
            rng.choice(EVENT_TYPES), oid,
            unit_id=rng.choice(op_units) if op_units else None)

    # --- the trap events ---

    # OP-2742 crossed into the service-review band six days ago at 99.31%.
    add(TODAY - timedelta(days=6), 8, 15, "availability_warning", "OP-2742",
        metadata={"availability_30d": 0.9931, "band": "service_review",
                  "threshold": 0.995})
    add(TODAY - timedelta(days=10), 6, 40, "case_opened", "OP-2742",
        unit_id="RU-4118", case_id="CS-8312",
        metadata={"severity": "critical", "fault_code": "TX-PWR-LOW"})

    # OP-2743: dispatch keeps failing on an expired site access permit.
    add(TODAY - timedelta(days=3), 9, 5, "dispatch_failed", "OP-2743",
        metadata={"reason": "site access permit expired", "retry": "pending",
                  "action": "operator must renew the permit via the portal"})

    # OP-2745 never became an operator — declined at RF site survey.
    add(TODAY - timedelta(days=7), 14, 30, "onboarding_declined", "OP-2745",
        metadata={"applicant_name": "Verdemar Offshore Systems",
                  "reason": "RF site survey failed: co-channel interference from "
                            "an adjacent installation exceeded limits"})

    # OP-2751 is the "most failed dispatches" answer: 4, against 1 each elsewhere.
    for days_back, reason in [
        (19, "no site contact available"),
        (14, "no site contact available"),
        (8, "vessel traffic closed the access channel"),
        (4, "no site contact available"),
    ]:
        add(TODAY - timedelta(days=days_back), 10, 0, "dispatch_failed", "OP-2751",
            metadata={"reason": reason})

    # One-offs elsewhere, including a red herring that was retried successfully.
    add(TODAY - timedelta(days=16), 11, 30, "dispatch_failed", "OP-2759",
        metadata={"reason": "weather hold", "retry": f"succeeded {ago(15)}"})
    add(TODAY - timedelta(days=15), 8, 0, "field_visit_completed", "OP-2759")

    events.sort(key=lambda e: e["timestamp"])
    return events


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------

TICKET_TOPICS = [
    ("calibration window request", "Asked whether calibration can be moved outside "
     "peak traffic hours. Confirmed the standard 4-hour maintenance window and "
     "that Priority plans may schedule it overnight."),
    ("spare part lead time", "Wanted to know the lead time on a replacement "
     "transmitter module. Quoted the standard advance-replacement terms."),
    ("firmware upgrade question", "Asked whether the 5.0.0 firmware is mandatory. "
     "Explained the 12-month support window on the previous major version."),
    ("portal access", "New engineer needed portal access. Directed the operator's "
     "admin to issue the invite themselves; Northbeam does not create accounts."),
    ("availability report query", "Asked how the 30-day availability figure is "
     "calculated and what counts as excluded downtime."),
    ("clutter complaint", "Reported increased sea clutter returns. Advised on STC "
     "curve adjustment and scheduled a calibration check."),
    ("invoice question", "Queried the annual service fee line on the renewal."),
    ("training request", "Asked about operator refresher training for new staff."),
]


def build_tickets(operators: dict, cases: dict) -> list[dict]:
    tickets: list[dict] = []
    oids = [o for o in operators if o != "OP-2742"]

    # THE STALE TICKET: closed four days before CS-8312's window expired.
    tickets.append({
        "id": "TKT-3108",
        "operator_id": "OP-2742",
        "subject": "Critical fault on the main mast array (CS-8312)",
        "status": "closed",
        "opened_on": ago(10),
        "closed_on": ago(7),
        "body": (
            "Operator reported degraded detection on the Cape Solvang main mast "
            "(RU-4118) with fault code TX-PWR-LOW. Service case CS-8312 raised at "
            "critical severity.\n\n"
            "A field engineer has been assigned and the operator has been notified. "
            "Treating this as handled from the support desk side — closing the "
            "ticket.\n\n"
            f"NOTE FOR REVIEWERS: this ticket was closed on {ago(7)}. The SLA "
            "response on CS-8312 was not logged before the window, so the case "
            "record is the authority on where this actually stands, not this "
            "ticket."
        ),
    })

    # The declined applicant — the only place the OP-2745 name is written down
    # besides the event log.
    tickets.append({
        "id": "TKT-3103",
        "operator_id": "OP-2745",
        "subject": "Verdemar Offshore Systems — site survey outcome",
        "status": "closed",
        "opened_on": ago(13),
        "closed_on": ago(7),
        "body": (
            "Verdemar Offshore Systems (applicant reference OP-2745) applied for a "
            "two-unit maritime installation.\n\n"
            "The RF site survey failed: co-channel interference from an adjacent "
            "installation exceeded the limits in the commissioning standard. The "
            f"application was declined on {ago(7)} and no equipment was shipped.\n\n"
            "Verdemar is not an operator on the platform and has no units, no "
            "support plan and no service cases. They may reapply once the "
            "interference is resolved."
        ),
    })

    tickets.append({
        "id": "TKT-3121",
        "operator_id": "OP-2743",
        "subject": "Why is our response time different from the contract?",
        "status": "closed",
        "opened_on": ago(53),
        "closed_on": ago(53),
        "body": (
            "Kettleworth asked why they are seeing a 4-hour response target when "
            "their Standard plan states 8 hours.\n\n"
            "Explained the 90-day commissioning burn-in: every newly commissioned "
            "site gets enhanced response and a spares deposit for the first 90 days "
            "after acceptance, regardless of plan. Kettleworth was onboarded "
            f"{operators['OP-2743']['onboarded_on']}, so they remain in the burn-in "
            "window. This is standard for new sites and is not a reflection of "
            "account standing."
        ),
    })

    # Filler, so `list_tickets` has realistic volume per operator.
    for i in range(52):
        oid = oids[i % len(oids)]
        topic, body = TICKET_TOPICS[i % len(TICKET_TOPICS)]
        opened = TODAY - timedelta(days=rng.randint(20, 400))
        tickets.append({
            "id": f"TKT-{3131 + i}",
            "operator_id": oid,
            "subject": f"{operators[oid]['name']} — {topic}",
            "status": "closed",
            "opened_on": iso(opened),
            "closed_on": iso(opened + timedelta(days=rng.randint(0, 4))),
            "body": f"{body}\n\nOperator: {operators[oid]['name']} ({oid}).",
        })

    return tickets


# ---------------------------------------------------------------------------
# Ground-truth aggregates
# ---------------------------------------------------------------------------


def build_facts(operators, units, cases, events) -> dict:
    dispatch_fails: dict[str, int] = {}
    for e in events:
        if e["event_type"] == "dispatch_failed":
            dispatch_fails[e["operator_id"]] = dispatch_fails.get(e["operator_id"], 0) + 1
    top_dispatch = max(dispatch_fails.items(), key=lambda kv: kv[1])

    # "Still actionable and due by month end" — open, not yet breached, due on or
    # before MONTH_END. Deliberately excludes cases whose window has passed.
    open_by_month_end = [
        cid for cid, c in cases.items()
        if not c["response_logged"]
        and iso(TODAY) <= c["sla_response_due"] <= MONTH_END
    ]

    at_or_below = sorted(
        oid for oid, o in operators.items() if o["availability_30d"] <= 0.995
    )

    open_cases = {cid: c for cid, c in cases.items() if not c["response_logged"]}
    largest = max(open_cases.items(), key=lambda kv: kv[1]["parts_cost_cents"])

    breached = sorted(
        cid for cid, c in cases.items()
        if not c["response_logged"] and c["sla_response_due"] < iso(TODAY)
    )

    case_counts: dict[str, int] = {}
    for c in cases.values():
        case_counts[c["operator_id"]] = case_counts.get(c["operator_id"], 0) + 1

    downtime_by_operator: dict[str, int] = {}
    for u in units.values():
        downtime_by_operator[u["operator_id"]] = (
            downtime_by_operator.get(u["operator_id"], 0) + u["downtime_minutes_30d"])
    top_downtime = max(downtime_by_operator.items(), key=lambda kv: kv[1])

    return {
        "today": iso(TODAY),
        "month_end": MONTH_END,
        "counts": {
            "operators": len(operators), "units": len(units),
            "cases": len(cases), "events": len(events),
        },
        "most_failed_dispatches": {"operator_id": top_dispatch[0],
                                   "name": operators[top_dispatch[0]]["name"],
                                   "count": top_dispatch[1]},
        "open_cases_due_by_month_end": {"count": len(open_by_month_end),
                                        "case_ids": sorted(open_by_month_end)},
        "operators_at_or_below_995": {
            "operator_ids": at_or_below,
            "names": [operators[o]["name"] for o in at_or_below],
            "near_miss": {"operator_id": "OP-2764",
                          "availability_30d": operators["OP-2764"]["availability_30d"]},
        },
        "largest_open_case": {"case_id": largest[0],
                              "parts_cost_cents": largest[1]["parts_cost_cents"],
                              "operator_id": largest[1]["operator_id"]},
        "breached_sla_cases": breached,
        "case_counts_by_operator": case_counts,
        "most_downtime_operator": {"operator_id": top_downtime[0],
                                   "name": operators[top_downtime[0]]["name"],
                                   "downtime_minutes_30d": top_downtime[1]},
    }


# ---------------------------------------------------------------------------


def main() -> None:
    DATA.mkdir(exist_ok=True)
    TICKETS.mkdir(exist_ok=True)
    for stale in TICKETS.glob("*.md"):
        stale.unlink()

    operators = build_operators()
    units = build_units(operators)
    cases = build_cases(operators, units)
    events = build_events(operators, units, cases)
    tickets = build_tickets(operators, cases)
    facts = build_facts(operators, units, cases, events)

    (DATA / "operators.json").write_text(json.dumps(operators, indent=2) + "\n")
    (DATA / "units.json").write_text(json.dumps(units, indent=2) + "\n")
    (DATA / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    (DATA / "event_log.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events))

    index = {}
    for t in tickets:
        slug = t["subject"].lower().replace(" ", "-")
        slug = "".join(ch for ch in slug if ch.isalnum() or ch == "-")[:60]
        fname = f"{t['id']}_{slug}.md"
        (TICKETS / fname).write_text(
            f"# {t['id']} — {t['subject']}\n\n"
            f"- operator: {t['operator_id']}\n"
            f"- status: {t['status']}\n"
            f"- opened: {t['opened_on']}\n"
            f"- closed: {t['closed_on']}\n\n"
            f"{t['body']}\n"
        )
        index[t["id"]] = {"file": fname, "operator_id": t["operator_id"],
                          "subject": t["subject"], "status": t["status"],
                          "opened_on": t["opened_on"], "closed_on": t["closed_on"]}
    (DATA / "tickets_index.json").write_text(json.dumps(index, indent=2) + "\n")
    (DATA / "generated_facts.json").write_text(json.dumps(facts, indent=2) + "\n")

    print(f"operators {len(operators)}  units {len(units)}  cases {len(cases)}  "
          f"events {len(events)}  tickets {len(tickets)}")
    print(json.dumps(facts, indent=2))


if __name__ == "__main__":
    main()
