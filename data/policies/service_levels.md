# Service Levels

Applies to every operator with an active service agreement. All times are in the
operator's local time at the installed site.

## Support plans

| Plan | Annual coverage | Critical response | Major response | Minor response | Availability commitment |
|---|---|---|---|---|---|
| Standard | 08:00–18:00, Mon–Fri | 8 hours | 2 business days | 5 business days | 99.0% |
| Priority | 24/5 | 4 hours | 1 business day | 3 business days | 99.5% |
| Mission | 24/7/365 | 1 hour | 8 hours | 2 business days | 99.7% |

Response means a qualified engineer has made contact and logged an initial
assessment against the service case. It does **not** mean the fault is fixed.
Time to restore is tracked separately and is not contractually capped.

Plan changes take effect at the start of the next billing month. There is no
mid-month proration.

## Availability bands

Availability is the rolling 30-day percentage of scheduled operating time during
which a unit produced usable data. It is recalculated nightly. Only the current
30-day figure is retained — Northbeam does not keep a month-by-month history.

| Band | 30-day availability | What happens |
|---|---|---|
| Normal | above 99.5% | No action. |
| Service review | 99.0% to 99.5% inclusive | Account flagged `availability_watch`. A joint review is scheduled and a remediation plan is agreed. Enhanced response is applied at no charge. |
| Contract review | below 99.0% | Formal contract review. Service credits are assessed and a spares deposit may be required. |

Crossing into service review is **not** a contract review and does not by itself
trigger service credits. The two bands are distinct and an account sitting at,
for example, 99.3% is in service review only.

## Service credits

Credits apply only when the **contractual response target** for a case was
missed, and only in the contract review band or on Mission plans. They are
calculated as a percentage of the monthly service fee for the affected unit:

| Response target missed by | Credit |
|---|---|
| up to 2× the target | 5% |
| 2× to 4× the target | 10% |
| more than 4× the target | 20% |

Credits are capped at 20% of the monthly fee per unit per month. They are
requested by the operator through the portal and applied to the next invoice.
Credits are never issued automatically and support engineers cannot grant them.

## Excluded downtime

The following do not count against availability:

- scheduled maintenance inside an agreed window
- operator-caused outages (site power, site network, unauthorised configuration
  changes)
- force majeure, including storm damage to the mast or radome
- downtime while a unit is awaiting an operator-supplied site access permit

## Commissioning burn-in

For the first **90 days** after site acceptance, every newly commissioned site is
placed on **enhanced response** (one band better than its plan) and carries a
**10% spares deposit**, regardless of plan. This is standard for all new sites and
is not a reflection of account standing. Both revert automatically at day 90 if
no unresolved critical faults remain open. See `onboarding_and_commissioning.md`.
