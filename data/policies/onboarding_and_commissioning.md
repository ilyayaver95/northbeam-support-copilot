# Onboarding and Commissioning

## The path from application to live site

| Stage | Owner | Typical duration |
|---|---|---|
| 1. Application and commercial review | Sales | 5 business days |
| 2. RF site survey | Field engineering | 10 business days |
| 3. Contract and plan selection | Sales | 5 business days |
| 4. Installation | Field engineering | 3–15 business days per unit |
| 5. Site acceptance test (SAT) | Joint | 1–2 business days |
| 6. Commissioning burn-in | Support | 90 days |

An operator becomes an operator at **site acceptance**, not at contract signature.
Until SAT passes, the applicant has no operator record, no support plan, no units
and no service cases.

## RF site survey

The survey is mandatory and cannot be waived. It checks:

- co-channel and adjacent-channel interference against the licensed band
- line of sight and terrain shadowing across the required coverage arc
- mast loading, grounding, and lightning protection
- available site power and network path
- physical access for a service vehicle and lifting equipment

A survey can fail. The most common cause is **co-channel interference from an
adjacent installation exceeding the limits in the commissioning standard**, which
cannot be engineered around from the Northbeam side. An application that fails
the survey is **declined**, no equipment is shipped, and the applicant reference
is closed. Declined applicants may reapply once the underlying condition is
resolved; a new survey is required.

## Site acceptance test

SAT verifies detection probability, range accuracy, azimuth accuracy, and false
alarm rate against the model specification, with the operator present. A unit
that fails SAT is not accepted and does not enter the availability calculation
until it passes.

The 24-month warranty and the 90-day burn-in both start on the SAT pass date.

## Commissioning burn-in

For 90 days after site acceptance every new site gets:

- **enhanced response** — one severity band better than the contracted plan
- a **10% spares deposit** held against the account
- **free advance replacement** on any LRU
- weekly availability reporting instead of monthly

All four revert automatically at day 90 provided no critical fault is still open.
Burn-in is applied to every new site without exception. It is a standard part of
commissioning and says nothing about the operator's standing, plan, or risk.

## Restricted installations

Northbeam does not supply or support installations where:

- the licensed frequency allocation is not held by the operator
- the site sits inside a protected radio-astronomy quiet zone
- the intended use is weapons cueing or fire control
- export control prohibits supply to the destination

These are refused at application review and never reach the survey stage.
