# Northbeam Support Copilot

An internal support copilot for a fictional radar company. Northbeam Radar
Systems supplies and services surveillance radar to airports, seaports and
meteorological agencies; the copilot's user is a **Northbeam support engineer**
working an operator's case — deadlines, availability thresholds, spare parts,
policy — not the customer.

It is a tool-calling agent over a synthetic but internally consistent world: 33
operators, 213 installed units, 18 service cases, 225 event-log entries, 55 past
tickets and seven policy documents.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set LLM_MODEL and the matching provider key

pytest -q                     # 196 offline tests, no API key needed, ~1s
python app.py                 # local web UI -> http://127.0.0.1:5000
python copilot.py "Is case CS-8312 still inside its response window?"
```

First run downloads the MiniLM embedding model (~90MB).

---

## What it does

```
question
   |
   v
[1] bounded tool loop  -- the model picks tools, Python runs them,
   |                      real results become the evidence block
   v
[2] one structured call -- evidence in, Answer out
   |
   v
[3] refusal.classify()  -- deterministic rules decide the outcome where the
   |                       right answer is enumerable; the model's own
   |                       structured outcome stands where it is not
   v
[4] observability       -- one trace line per call, feeding the KPI dashboard
   |
   v
Answer(text, sources, outcome, decline_reason, tool_calls)
```

Twelve tools in three layers:

| Layer | Tools | Why it is separate |
|---|---|---|
| Records | `find_operator` `get_operator` `get_unit` `list_units` `get_case` `list_cases` `list_tickets` `get_ticket` `read_event_log` | Each reads ONE thing, so a citation maps to a real record |
| Calculation | `aggregate_records` `compute` | The model decides *what* to compute; Python computes it |
| Retrieval | `search_policies` | Hybrid BM25 + embedding search over the policy corpus |

Every tool is a read. There is no tool that changes anything — which is why the
refusal layer can treat "restart that unit" as a fact about capability rather
than a judgement call.

---

## The design question this project is really about

For every decision in an agent, ask: **is the right answer enumerable?**

- **Enumerable** → code. Testable, reproducible, instant, free.
- **Genuinely contextual** → the model. Accept the variance, and measure it.

The tempting mistake is letting the model own things in the first column just
because it *can*.

| Decision | Owner | Why it sits there |
|---|---|---|
| Which tools to call, with which ids | **model** | Open-ended. Enumerating it would be a brittle intent router. |
| How to phrase the answer | **model** | The thing language models are actually for. |
| Decline: protected values (site access codes, staff PII, API keys, raw signal data) | **code** | A closed list of things Northbeam never exposes. Doesn't vary with context, so shouldn't vary with a sample. |
| Decline: state-changing actions | **code** | The copilot has only read tools. A capability fact. |
| Decline: "that record doesn't exist" | **code** | Provable from the evidence. |
| Decline: privacy scope, regulatory advice, unknowable futures | **model** | Genuinely contextual — whose data it is depends on whose case it is. |
| All arithmetic, counting, ranking, thresholds | **code** | Exactly one right answer. Never a sample. |
| Which tools actually ran | **code** | Recorded from execution, never self-reported. |
| Which citations are well-formed | **code** | Derived from the id shape, not asked of the model. |
| Loop bounds, retries, caching, tracing | **code** | Infrastructure. |

The outcome: **8 of the 13 declines in the eval suite are decided in code**
(62%), with **zero false positives** across all 77 questions — pinned by a test
that runs in milliseconds rather than a hundred model calls. The other five are
privacy-scope, regulatory and unknowable-future questions that genuinely need
judgement, so they go to the model.

`DESIGN.md` has the full rationale, the alternatives rejected, and what each
choice costs.

---

## The calculation layer

The record tools all answer "tell me about ONE thing". Questions like *which
operator had the most failed dispatches* or *which open case has the biggest
parts cost* need filtering, grouping and arithmetic across a whole dataset —
precisely where language models are least reliable.

```python
aggregate_records(
    dataset="cases",
    metric="max",
    field="parts_cost_cents",
    filters=[{"field": "response_logged", "op": "eq", "value": False}],
)
# -> value: 317500, records: [{case_id: "CS-8321", ...}],
#    computation: "max(parts_cost_cents) over cases where
#                  response_logged eq False — 10 record(s) matched"
```

Three things make it trustworthy: the number is computed in Python, the record
ids behind it come back so the answer stays citable, and the `computation`
string says exactly what ran so a human can audit it. `compute` handles the
derived arithmetic — percentages, cents to currency, minutes to hours — as an
AST walk over a whitelist rather than `eval`.

---

## How I know it works

Two layers, because they answer different questions on different cadences.

### `tests/` — 196 offline tests, no API key, about a second

Everything with a knowable right answer. Aggregation expectations are computed
from the raw data inside the test rather than pasted in, so they stay true when
the world is regenerated. Includes the guardrails that matter most: zero
false-positive declines across every eval question, and a test that fails if a
refactor quietly hands the code-decided declines back to the model.

```bash
pytest -q
```

### `evals/` — 77 behavioural cases across six categories

```bash
python -m evals.runner investigation --verbose
python -m evals.run_all --save after.json
python monitoring.py compare before.json after.json   # exits 1 on regression
```

| Category | Cases | What it isolates |
|---|---|---|
| `policy_lookup` | 12 | Reading a fact when the question and the document share no vocabulary |
| `synthesis` | 8 | Combining facts across two or more documents |
| `tool_use` | 12 | Calling the right tool with the right id |
| `investigation` | 15 | Reaching the right conclusion, including where the shallow read is wrong |
| `honesty` | 10 | Reporting a gap without fabricating and without over-declining |
| `boundaries` | 20 | Declining what should be declined — and **not** what merely sounds like it |

Grading is deterministic and binary. Nothing is judged by a model.

### KPIs

**Quality**, from graded runs — these decide whether a change ships:
pass rate per category, **over-decline rate** (refused something answerable — the
worst failure for a support tool, because it looks safe), **under-decline rate**,
hedge rate, citation coverage, malformed-citation rate.

**Operational**, from the trace log — these tell you it is degrading in
production, where nothing is labelled: latency p50/p95, tool calls and steps per
answer, step-limit-hit rate, ungrounded-answer rate, tool error rate, decline
rate and **what share was decided in code**, error rate, tokens per answer.

```bash
python monitoring.py ops
```

All of it is live on the dashboard tab of the web app.

---

## The world

Built by `scripts/generate_world.py` — deterministic, fixed seed, regenerate
rather than hand-editing. `data/generated_facts.json` holds the ground-truth
aggregates the eval suites assert against.

It is built around traps: places where the shallow reading and the correct
reading disagree, so a copilot that skims is visibly wrong rather than plausibly
wrong.

| Trap | The shallow read | The right read |
|---|---|---|
| `CS-8312` | Ticket TKT-3108 says "handled" | Closed 05-18, before the 05-22 window expired. Response never logged. Breached. |
| `OP-2742` | 99.31% availability, sound the alarm | That is the 99.0–99.5% *service review* band, not contract review |
| `OP-2743` | On 4-hour response, must be a problem account | 76 days into a 90-day commissioning burn-in. Every new site gets it. |
| `OP-2745` | Verdemar Offshore, look up their plan | Declined at RF site survey. Not an operator. Has no plan to look up. |
| `OP-2764` | 99.52% — below the threshold | Just *above* it. A deliberate near-miss for off-by-one threshold logic. |
| `RU-49999` | — | Does not exist |

Today is frozen at **2026-09-14**. Every deadline in the data is relative to it,
so the date arithmetic is reproducible.

---

## Layout

```
copilot.py         the pipeline: ask() -> Answer
schema.py          the Answer contract
prompts.py         both prompts (there is no refusal-judging prompt — see refusal.py)
refusal.py         deterministic outcome rules
toolkit.py         tool registry + the schemas the model routes on
observability.py   one trace per call
monitoring.py      KPIs and the regression gate
app.py + web/      local web UI
tools/             records, aggregation, arithmetic, retrieval
evals/             grader, runners, and the six suites
tests/             offline test suite
scripts/           the world generator
data/              generated records + the policy corpus
```

The domain, the data, the policy corpus and all the code are original to this
project. Everything is synthetic — no real company, customer, or personal data
appears anywhere in it.
