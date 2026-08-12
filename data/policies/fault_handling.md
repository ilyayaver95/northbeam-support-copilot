# Fault Handling and Escalation

## Severity classification

Severity is set from the operational impact, not from how alarming the fault
code looks.

| Severity | Definition | Examples |
|---|---|---|
| Critical | Unit is not producing usable data, or detection performance is degraded to the point the operator has suspended reliance on it. | `TX-PWR-LOW` below the licensed minimum, `PSU-FAULT` on a single-supply unit, total `COMMS-LINK-DOWN`. |
| Major | Measurable degradation, but the unit remains usable with a workaround. | `RX-NOISE-HIGH`, `MTI-DEGRADED`, `AZ-ENC-DRIFT` within correctable limits. |
| Minor | Cosmetic, redundant-component, or monitoring-only faults. | `FAN-FAIL` on a redundant fan, `WG-PRESSURE-LOW` above the alarm floor. |

An operator may request a severity increase. Reclassification downward requires
agreement from the operator and must be noted on the case.

## The SLA response clock

The clock starts when the service case is created, whether it was raised by an
operator or opened automatically from a unit alarm. It stops when a qualified
engineer logs an initial assessment on the case. Nothing else stops it — not an
acknowledgement, not an engineer being assigned, not a ticket being closed at
the support desk.

The **case record** is the authority on where a fault stands. Support tickets are
correspondence about a case and are frequently closed before the case is
resolved. A closed ticket never implies the SLA was met.

## When a response window is missed

Once `sla_response_due` has passed with no response logged, the case is
**breached**. Missing the window does not close the case and does not remove the
obligation to respond — the work continues, and the case stays open until the
fault is resolved.

What follows a breach:

1. The case is escalated to the regional service manager automatically.
2. The operator is notified within one business day, with a revised commitment.
3. The operator may request service credits under `service_levels.md`.
4. The breach is included in the next quarterly service review.

There is no mechanism to retroactively meet a missed window, and no way to
suppress the escalation.

## Escalation path

| Stage | Owner | Trigger |
|---|---|---|
| 1 | Support engineer | Case raised |
| 2 | Regional service manager | Response window breached, or operator requests escalation |
| 3 | Head of field service | Critical case open beyond 72 hours |
| 4 | Account director | Second breach on the same unit within 30 days |

## Recurring faults

Three or more cases with the same fault code on the same unit within 90 days is
a **recurring fault**. Recurring faults are escalated to engineering regardless
of individual severity, and the unit is scheduled for a full diagnostic visit
rather than another component swap.
