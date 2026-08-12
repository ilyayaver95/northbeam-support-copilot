# Maintenance and Calibration

## Calibration intervals

| Model | Type | Interval | Grace period |
|---|---|---|---|
| NB-410 | C-band weather doppler | 6 months | 30 days |
| NB-620 | X-band marine surveillance | 12 months | 45 days |
| NB-870 | S-band primary surveillance | 12 months | 30 days |
| NB-880 | S-band secondary surveillance | 12 months | 30 days |

A unit past its interval but inside the grace period is flagged
`calibration_due` and remains in service. Past the grace period it is flagged
`calibration_overdue`, and **downtime from an overdue calibration is not
excluded from the availability calculation** — it counts against the operator.

Calibration is performed on site by a Northbeam field engineer. Operators cannot
self-certify calibration, and a third-party calibration certificate does not
reset the interval.

## Maintenance windows

Standard preventive maintenance takes a **4-hour window**. Priority and Mission
operators may schedule it overnight at no extra charge; Standard operators may
request an out-of-hours window at the published call-out rate.

Maintenance inside an agreed window is excluded from availability. Maintenance
that overruns its agreed window is excluded only for the agreed duration — the
overrun counts against availability.

Windows must be agreed at least **5 business days** in advance. Northbeam may
move a window with 48 hours' notice; the operator may move it with 24 hours'
notice, once per window.

## Firmware

Firmware follows a two-track release model:

- **Stable** — the current recommended release. Today that is `5.0.0`.
- **Extended support** — the previous major version, supported for **12 months**
  after the successor's release. Today that is the `4.2.x` line.

Anything older than extended support is unsupported. Faults on unsupported
firmware are handled on a commercial-best-efforts basis and are outside the
availability commitment.

Firmware upgrades are not mandatory, with one exception: a release marked
**mandatory safety** must be applied within 30 days. Northbeam does not push
firmware to a unit without an agreed window — every upgrade is scheduled.

## Site conditions

The operator is responsible for site power, site network, physical security,
access permits, and keeping the radome clear of accumulated salt, ice, and
debris. Faults traced to site conditions are chargeable at the published call-out
rate and the resulting downtime is not excluded from availability.

Northbeam publishes no guaranteed mean time between failures (MTBF) figure for
any model. Reliability varies too widely with siting and environment for a single
number to be meaningful, so none is quoted in contracts or in the portal.
