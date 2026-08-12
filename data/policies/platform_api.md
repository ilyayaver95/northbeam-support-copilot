# Fleet Portal API

Base URL: `https://api.northbeam.example/v3`
Current stable version: **v3**. Version v2 is in extended support until
2027-01-31.

## Authentication

All requests use a bearer token in the `Authorization` header:

```
Authorization: Bearer nbk_live_...
```

Keys are issued by an operator administrator in the portal, under
**Settings → API keys**. Northbeam support staff cannot see, retrieve, or issue
API keys — a lost key is rotated by the operator's own administrator. Keys are
scoped to a single operator and cannot read another operator's fleet.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/units` | List units for the authenticated operator |
| `GET` | `/units/{unit_id}` | One unit, including current status and firmware |
| `GET` | `/units/{unit_id}/availability` | Rolling 30-day availability figure |
| `GET` | `/cases` | List service cases |
| `POST` | `/cases` | Raise a service case |
| `PATCH` | `/cases/{case_id}` | Update operator-side fields on a case |
| `POST` | `/cases/{case_id}/rma` | Raise an RMA against a case |
| `GET` | `/maintenance-windows` | List agreed windows |
| `POST` | `/maintenance-windows` | Request a window |
| `DELETE` | `/maintenance-windows/{id}` | Cancel a window |

Severity, `sla_response_due`, and the response log are Northbeam-controlled and
are read-only over the API. `PATCH /cases/{case_id}` will return `403` if the
request body touches them.

`POST /cases/{case_id}/rma` returns `409` if the case already has an open RMA,
and `422` if the RMA is raised more than 21 days after the replacement shipped.

## Idempotency

Send an `Idempotency-Key` header on any `POST`. Northbeam remembers the key for
**24 hours** and returns the original response for a repeat, so a retried case
creation does not raise a duplicate.

## Rate limits

| Plan | Sustained | Burst |
|---|---|---|
| Standard | 5 req/s | 20 |
| Priority | 20 req/s | 60 |
| Mission | 50 req/s | 150 |

Exceeding the limit returns `429` with a `Retry-After` header. Limits are per
operator, not per key.

## Webhooks

Subscribe in the portal under **Settings → Webhooks**. Available events:

| Event | Fires when |
|---|---|
| `unit.alarm` | A unit raises an alarm |
| `unit.offline` | A unit stops reporting |
| `unit.restored` | A unit resumes reporting |
| `case.opened` | A service case is created |
| `case.response_logged` | An engineer logs the initial assessment |
| `case.sla_breached` | A response window passes with no response logged |
| `availability.warning` | 30-day availability crosses into service review |
| `calibration.due` | A unit enters its calibration grace period |

Every delivery carries an `X-Northbeam-Signature` header — an HMAC-SHA256 of the
raw request body using the subscription's signing secret. Verify it against the
raw body before parsing. Deliveries are retried with exponential backoff for
24 hours; a `2xx` inside 5 seconds counts as delivered.

## Data retention over the API

- Service cases and their history: retained for the life of the agreement.
- Availability: **current 30-day figure only**. There is no endpoint for
  historical availability, and no month-by-month series is stored.
- Raw signal recordings (IQ data): retained **72 hours**, then deleted. They are
  never exposed over the API and are accessible only to field engineering during
  an active investigation.

## Status page

Platform status is published at `https://status.northbeam.example`. Northbeam
does not publish a guaranteed uptime percentage or SLA for the portal or the API
itself — the availability commitments in `service_levels.md` cover the installed
radar units, not the portal.
