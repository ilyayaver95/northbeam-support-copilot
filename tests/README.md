# tests/

Fast, offline, deterministic. **No API key, no network, no model calls** — the
whole suite runs in about a second, so it can gate every commit.

```bash
pip install -r requirements.txt
pytest -q
```

## Why this is separate from `evals/`

The two answer different questions on different cadences:

| | `tests/` | `evals/` |
|---|---|---|
| asks | is the deterministic machinery correct? | is the system's behaviour good? |
| needs | nothing | an API key and ~77 model calls |
| verdict | exact — pass or fail, not negotiable | statistical, smoothed with `--samples` |
| cadence | every commit | before shipping a change |

Anything with a knowable right answer belongs here. The aggregation tool must
return exactly 10 for a question whose answer is 10 — that is a unit test, not
something to verify by reading model prose.

## The files

**`test_aggregate.py`** — the calculation layer. Expectations are computed from
the raw data inside the test rather than pasted in, so they survive
regenerating the world. Several cross-check against `data/generated_facts.json`;
if the aggregation layer and the generator disagree, one of them is broken.

**`test_compute.py`** — arithmetic correctness, and the sandbox boundary. The
expression string is written by a model, so "no names, no calls, no imports, no
exponent bombs" is tested as carefully as the maths.

**`test_refusal.py`** — the deterministic outcome rules. Three tests carry most
of the weight:

- `test_no_rule_fires_on_any_answerable_eval_question` — zero false positives
  across all 77 questions. Over-declining is the worst failure mode for a
  support tool, so widening a pattern too far fails here in milliseconds
  instead of after a hundred model calls.
- `test_rules_never_talk_a_declinable_question_into_answering` — the regression
  test for a real bug: rule 3 once laundered genuine declines into answers.
- `test_code_decides_a_meaningful_share_of_declines` — fails if a refactor
  quietly hands everything back to the model, which would make the determinism
  claim untrue while every other test still passed.

**`test_tools.py`** — the record tools, the store, and the grader. Covers that a
missing record is *reported* rather than invented (which every honesty case
depends on), that the traps are actually present in the generated data, and that
the grader itself is correct — a broken grader makes every eval number
meaningless in the most convincing possible way.

**`test_contracts.py`** — the wiring that rots silently. Every registered tool
has a schema and vice versa; every declared property is a real parameter; every
parameter without a default is marked required; no tool looks like it mutates
anything; every eval suite loads, has unique ids, and expects only tools and
documents that exist.

**`test_monitoring.py`** — the KPI maths and the regression gate. A monitoring
layer that reports wrong numbers is worse than none, because you would ship on
it; and a gate that never fails is decoration, so the failing path is tested as
carefully as the passing one.
