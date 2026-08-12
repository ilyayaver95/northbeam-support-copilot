# Design notes

Every row here points at a real file in this repo. Read alongside `README.md`.

---

## The organising rule

For each decision in the pipeline, ask: **is the right answer enumerable?**

- **Enumerable** → code. Testable, reproducible, instant, free.
- **Genuinely contextual** → the model. Accept the variance, and measure it.

Most of the interesting choices below are applications of that one rule. The
temptation an agent framework encourages is to let the model own things in the
first column simply because it can.

---

## Core choices

| Decision | Why | What I rejected | What it costs |
|---|---|---|---|
| **Hand-rolled loop** — `litellm.completion()` + `instructor`, no agent framework | One bounded loop over twelve tools and seven documents. A framework's abstraction cost exceeds its benefit at this size, and I want to be able to defend every line. `litellm` and `instructor` already solve the two real problems: provider portability and schema conformance. | **LangGraph** — the closest conceptual match, but its real value (checkpointing, human-in-the-loop, graph inspection) is a scaled-production feature, and it does not reduce code for one loop. **LangChain AgentExecutor** — hides the loop mechanics I most want visible. **CrewAI** — built for autonomous multi-agent delegation; wrong shape for a fixed pipeline. **Raw provider SDK** — loses the one-line provider swap, which is how I found real failure modes (weak tool-calling on smaller models, rejected sampling params on reasoning models). | I maintain the loop bookkeeping. No checkpointing or resumability. No wall-clock timeout — only an iteration cap, so one slow tool can still stretch total latency. |
| **Twelve narrow tools**, dispatched by name through `REGISTRY` | Matches question granularity: most questions need one or two specific facts. Narrow descriptions are a precise routing signal; narrow returns make a citation map to one real record. Chaining is natural (`find_operator` → `list_cases` → `get_case`) and each hop is separately citable. `read_event_log` is operator-scoped by construction, so the access boundary is structural rather than a prompt instruction. | **One mega-tool** `query(question)` — hides all routing behind something the model cannot reason about via schema, and blurs which record was actually used. **A hardcoded intent router** — brittle, needs every question shape enumerated, and fails exactly on the paraphrases that matter. | Twelve schemas to keep in sync with twelve signatures. `tests/test_contracts.py` exists specifically because that drift is silent otherwise. |
| **`find_operator` as a resolution tool**, rather than a directory in the system prompt | The obvious shortcut is to paste all 33 operator names into the system prompt so the model can map a name to an id. That is tokens on every single call for something a tool does exactly, plus it makes the OP-2745 trap incoherent: an operator that does not exist cannot be absent from a list the model was handed. A resolution tool returns not-found honestly, which is the correct answer. | **Name directory in the prompt** — pays tokens forever and weakens the trap. **Fuzzy matching inside every tool** — the same logic copied five times. | One more hop before the first real read. Fuzzy matching can return candidates the model has to disambiguate. |
| **Calculation layer** — `tools/aggregate.py` + `tools/compute.py` | The record tools all answer "tell me about ONE thing". "Which operator had the most failed dispatches" would need 33 separate log reads — impossible inside `MAX_STEPS` — so the fallback is the model eyeballing records and doing arithmetic in prose, which is where it is least reliable. Now it is one call with the exact answer. Results carry the record ids behind the number, so an aggregate stays citable, and a `computation` string, so it is auditable. | **A generic `run_python(code)` tool** — strictly more powerful and strictly worse: arbitrary model-written code against the data, no schema to route on, nothing to unit-test. **Pre-computed fixed aggregates** — only answers the questions I thought of. **Leaving the maths to the model** — the failure being fixed. | A small filter DSL the model can still get wrong: a bad filter yields a confidently wrong number. Mitigated by the `computation` string being visible in the evidence and the UI. |
| **Outcome decided in code** — `refusal.py`, not a second model call | The obvious build is a second call that reads the question and answer and judges whether the copilot refused. That is one more round trip, one more source of variance, and a guess at something the system already knows. Rules run in priority order — protected value, state change, missing record, then the model's own structured outcome — and each reports which rule fired, so the code/model split shows up in the trace instead of being assumed. One fewer model call per question, and "why did it decline?" is a rule name rather than a re-run. | **A keyword hedge-phrase guard** — I have seen this fail badly: if the phrase list is copied from the grader's own list, the system grades against itself. These rules match the *request*, never the answer prose, and are validated for false positives against every eval question. **All-code declines** — tried it; privacy scope genuinely needs context the rules cannot see. **Keeping the LLM judge** — the thing removed. | Regexes over English will miss phrasings I did not anticipate; the model's own outcome is the safety net underneath. Two rules needed tightening after tests caught them — see below. |
| **`Answer` schema with an `outcome` enum**, and citations typed in code | "Did it refuse?" has more than two useful states over time (declined, escalated, partially answered), and an enum extends where a boolean needs a migration. Citations come back as a flat list and the policy/record split is *derived* from the id shape — asking the model to label each one is another thing to get wrong when a regex is exact. Malformed citations are surfaced rather than dropped, because a fabricated source is a hallucination worth seeing. | **`refused: bool`** — works, but paints you in. **Model-labelled citation types** — more prompt surface, more failure modes, no gain. | An enum is marginally more to explain than a boolean. |
| **Structured output via `instructor`** with `num_retries=4` | The grader depends on the exact schema, so the mechanism producing it has to guarantee conformance rather than usually manage it. `instructor` turns the pydantic class into the schema the model is told to fill — `Field(description=...)` is live prompt content — and validates and retries automatically, so the spec and the instruction are one artifact. | **JSON mode with hand parsing** — reintroduces the brittleness. **Free text plus an extraction pass** — another unreliable step. | Retry-until-valid adds latency on failure. `description=` strings are simultaneously documentation and prompt, so an innocent wording edit can change behaviour. |
| **Hybrid retrieval** — BM25 + embeddings, heading-aware chunks, adaptive document count | The corpus is tables and short sections; splitting on a fixed character count severs a threshold from the band it belongs to. BM25 catches literal terms (fault codes, `sla_response_due`, "advance replacement"); the embedding catches the paraphrase, since an engineer asks "how long till they have to answer", not "what is the response target". The document count follows the score spread, so single-fact questions get one document and synthesis questions get several. | **Fixed top-k cosine only** — loses the literal-term half and either starves synthesis questions or floods simple ones. **A stricter relevance floor** — trades away the recall the synthesis suite needs. | No absolute relevance floor: min-max normalisation always stretches scores to fill [0,1], so an irrelevant query still returns two documents with plausible scores. Grounding instructions in stage 2 cover that, not retrieval itself. |
| **Forced tool use when the first turn wants to answer with nothing** | An answer with no evidence behind it is the worst thing this system can emit: fluent, confident, invented. Weaker models occasionally answer a data question straight from the prompt on turn one. That is *detectable* — zero tool calls on the first turn of a question about records — so it is handled in code: re-issue that turn with `tool_choice="required"`. It moved a reproducible hallucination ("Northbeam does not retain open service cases") to a correct grounded count, and `forced_tool_rate_pct` on the dashboard shows how often the prompt is failing to hold on its own. | **Prompt instructions alone** — I wrote them, and they held about two times in three on `gpt-4o-mini`. **Rejecting the answer outright** — worse UX than simply making it go and look. **Forcing tools on every turn** — breaks the natural loop exit, since the model must be able to stop. | One extra model call on the turns where it fires. If a question genuinely needs no tool, the forced call is wasted — bounded, because it only ever fires once, on the first turn. |
| **Errors fed back as tool results**, never raised | One bad argument should not kill a multi-step investigation. Returning `{"error": ...}` on the same channel as a success lets the model correct itself inside the same loop and keeps the loop code free of special cases. It also matches the policy: a missing record is a normal fact to report, so code and prompt agree. | **Letting exceptions propagate** — aborts a recoverable investigation over one typo, and contradicts the honesty policy. **Per-tool retry/backoff/circuit-breaking** — right for real external systems; these are local JSON reads that do not fail transiently. | A genuine bug in my own tool code looks identical to a legitimate not-found. `ToolCall.ok` at least makes the failure countable. |
| **Answer cache keyed on a pipeline version** | Without the version in the key, a cached answer from before a change silently replays the old system through every eval run after it — the change looks like it did nothing. | **No cache** — slow and expensive to iterate. **Caching without a version** — the trap above. | Exact-match only, so no benefit on paraphrases. Bumping the version is manual, and forgetting is the failure mode; `tests/test_contracts.py` at least asserts the key is version-scoped. |
| **Two test layers**, not one | They answer different questions on different cadences. Unit tests cover everything with a knowable right answer — no key, no network, about a second, so they gate every commit. Evals cover behaviour, cost real model calls, and are statistical. Conflating them means either paying for model calls to check arithmetic, or checking arithmetic by reading prose. | **Evals as the only layer** — needs a key, costs money, and is statistical where aggregation should be exact. **A hosted tracing platform** — the right answer at real scale; here it is a dependency and an account for something JSONL does. | Two places to look when something breaks. |
| **Regression gate on per-category deltas** | Gating on the total pass rate hides the trade that matters most: a change that lifts the headline number while quietly breaking the boundaries suite. `monitoring.py compare` exits non-zero if any *category* regresses. | **Gating on the total** — hides exactly what I want to catch. **No gate** — the numbers become decoration. | Zero tolerance will occasionally flag temperature-1 jitter; `--tolerance` and `--samples` are the escape hatches. |

---

## Three bugs found by testing, not by reading

Worth recording, because all three were in code I had just argued was correct.

**An unknown filter field returned a confident zero.** `aggregate_records` on a
field that exists on no record — `status` on cases, which actually calls it
`response_logged` — matched nothing and returned `0`, which the model duly
reported as the answer. A silently wrong number is far worse than an error,
because it is indistinguishable from a right one. The layer now validates every
referenced field against the dataset and returns an error naming the real ones,
so the model can correct itself in the same loop. Found by running the thing,
not by a unit test — which is why the live smoke test is part of the routine and
not an afterthought.





**Rule 3 laundered genuine declines.** The "a missing record is an answer, not a
refusal" rule originally fired on *any* not-found anywhere in the evidence. So a
single failed lookup during a boundary-crossing request — asking for another
operator's fleet data, say — would flip a correct decline into an answer.
`test_rules_never_talk_a_declinable_question_into_answering` caught it. The rule
now requires the missing record to be one the *question actually named*, which
is the only situation where "there is no such record" answers what was asked.

**Rule 1 swallowed policy questions.** The protected-value patterns matched the
noun, so "how long do we keep the raw signal recordings?" — an ordinary policy
question — declined exactly like "send me the recording from RU-4118".
`test_no_rule_fires_on_any_answerable_eval_question` caught it. There is now a
category-question guard, and the two phrasings sit in the suite as a pair
(`honesty_006` and `boundaries_004`) so the distinction stays pinned.

Both are the same lesson: high-precision rules are worth having, and the way you
keep them high-precision is a test that runs against every question you have.

---

## Known limits

- **No wall-clock timeout.** `MAX_STEPS` bounds iterations, not seconds.
- **No multi-turn context.** Each `ask()` is one independent investigation, which
  matches how a support engineer uses it, but rules out follow-ups.
- **The trace log grows unbounded.** No rotation; KPIs are computed on read, so a
  very large log gets slow.
- **Retrieval has no absolute relevance floor.** An irrelevant query still returns
  two documents.
- **Policy lives in prompt text**, so it is not type-checked. A subtle wording
  change can break a passing case, and only the eval suite will tell me.
- **One model plays both stages.** Tiering — a cheap model for tool routing, a
  stronger one for the final answer — is a real optimisation I have not made,
  because one model keeps the debugging surface small.

---

## If I kept going

1. **Tier the models.** Stage 1 is routing; it does not need the strongest model.
   The trace log already carries the per-stage token counts to size the win.
2. **A held-out paraphrase set.** The visible suites are a dev set, and I have
   been iterating against them. Paraphrased cases I cannot see would tell me how
   much of the score is generalisation.
3. **Confidence-gated escalation.** When retrieval scores are flat and no tool
   returned a decisive record, say so and route to a human rather than
   committing. Right now the system always commits, which is correct for the
   traps and wrong for genuine ambiguity.
4. **Per-question regression tracking.** Traces already carry a stable `qid`;
   joining runs on it would show *which* questions a change helped or hurt, not
   just the category totals.
