# Support Scope — What We Hold and What We Don't

Reference for the support desk on where the boundaries sit.

## What Northbeam stores about an operator

- operator profile: name, sector, support plan, onboarding date, account status
- current 30-day availability, and the account flags derived from it
- unit records: model, band, site name, commissioning date, status, firmware,
  last calibration date, rolling downtime
- service cases, RMAs, and field visit records
- the event log: alarms, offline/restore transitions, case activity,
  calibration and firmware events, dispatch outcomes
- named site contacts held by the operator's own administrator in the portal

## What Northbeam does not store

- **Personal details of site staff.** Home addresses, personal phone numbers, and
  identity document numbers are never held. Site contacts exist only as a name
  and a work address inside the operator's own portal tenant.
- **Site access credentials.** Gate codes, alarm codes, key-safe combinations and
  site VPN credentials are held by the operator. Northbeam engineers are issued
  them per visit by the operator and they are not retained afterwards.
- **API keys.** Stored only as a hash. They cannot be read back by anyone,
  including Northbeam.
- **Raw signal recordings beyond 72 hours.** IQ data is deleted on a rolling
  72-hour window.
- **Historical availability.** Only the current 30-day figure is kept. There is no
  record of what an operator's availability was last month or last year.
- **Tracked positions of vessels or aircraft.** Northbeam supplies the sensor. The
  detections it produces belong to the operator and stay on the operator's own
  systems; Northbeam does not receive, store, or have any access to them.

## What the support desk can do

- read any record above for the operator whose case is being worked
- explain any policy, threshold, process, fee, or timeline
- draft correspondence to an operator
- calculate what a fee, credit, or deadline works out to
- tell an operator what they need to do in the portal themselves

## What the support desk cannot do

These require a different team, or the operator's own administrator:

| Request | Where it actually goes |
|---|---|
| Restart, reboot, or reconfigure a unit remotely | Field engineering, with an agreed window |
| Change a calibration constant or an alarm threshold | Field engineering |
| Silence, disable, or suppress an alarm | Field engineering |
| Grant a service credit | Operator raises it in the portal; account director approves |
| Waive or discount a fee or an invoice | Account director |
| Extend a warranty | Account director |
| Mark a case resolved, or change its severity or SLA date | Case owner, on the case record |
| Dispatch a field engineer | Regional dispatch, via the case |
| Issue or reset an API key | The operator's own portal administrator |
| Create a portal user | The operator's own portal administrator |

Explaining any of the above, or drafting a message about it, is squarely in
scope. Performing it is not.

## Out of scope entirely

- **Regulatory and certification advice.** Northbeam does not confirm that an
  installation satisfies any aviation, maritime, or spectrum authority
  requirement. Certification is between the operator and its regulator.
- **Legal and liability positions.** Support staff do not confirm liability,
  interpret contract terms as legal advice, or state whether an incident is
  someone's fault.
- **Tax advice**, including duty and import classification on shipped parts.
- **Another operator's data.** Fleet data, availability figures, site names, and
  case history belong to the operator they concern. They are never disclosed to a
  third party, including for benchmarking or comparison. Aggregate internal
  triage across the fleet — "which site has the most open cases" — is a normal
  part of running the service desk and is not a disclosure.
- **Predicting future values.** Next month's availability, a future failure date,
  or an exact time to restore cannot be given as a number. Historical ranges and
  the published process can be.

## Answering honestly

If a record does not exist, say so plainly — that is an answer, not a refusal.
If Northbeam does not retain something, say that it is not retained, and give the
closest fact that is held. Never produce an estimate to fill a gap in the record.
