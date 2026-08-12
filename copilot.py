"""copilot.py — the Northbeam Radar Systems support copilot.

    from copilot import ask
    ask("Is case CS-8312 still inside its response window?")

Pipeline, per question:

    1. bounded tool loop     the model picks tools, Python runs them, real
                             results become the evidence block
    2. one structured call   evidence in, Answer out
    3. refusal.classify()    deterministic rules decide the outcome where the
                             right answer is enumerable; the model's own
                             structured outcome stands where it isn't
    4. observability.record()  one trace line, feeding monitoring.py

What the MODEL decides, and what CODE decides — the central design choice:

    model | which tools to call, with which ids. Open-ended and context-driven;
          | enumerating it would be a brittle intent router.
    model | how to phrase the answer, and the contextual declines — whose data
          | it is, whether something is really a regulatory question.
    code  | all arithmetic, counting and ranking (tools/aggregate.py, compute.py)
    code  | declines for protected values and state-changing actions
    code  | "a record the question named does not exist" is an answer
    code  | which tools actually ran — recorded, never self-reported
    code  | which citations are well-formed, derived from the id shape
    code  | loop bounds, retries, caching, tracing

The rule: the model handles what needs judgement. Everything with a knowable
right answer runs in Python, where it is testable and reproducible.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import instructor
import litellm
from dotenv import load_dotenv
from litellm import completion

import observability
import refusal as refusal_policy
from prompts import ANSWER_PROMPT, GATHER_PROMPT, TODAY
from schema import Answer, ToolCall
from toolkit import COMPUTED_TOOLS, REGISTRY, TOOL_SCHEMAS

load_dotenv()

# Some reasoning models reject sampling parameters like `temperature` and want
# `max_completion_tokens` instead of `max_tokens`. Letting litellm drop what a
# provider doesn't support keeps this model-portable. Do NOT read this as
# determinism — those models run at temperature 1 and vary between runs, which
# is what the eval runner's --samples flag exists to smooth.
litellm.drop_params = True

MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

# Ceiling on tool-loop iterations. Six covers the deepest legitimate chain seen:
# resolve an operator, list its cases, read the one that matters, aggregate,
# convert, check a policy. It is a safety net, not the normal ending — the loop
# exits the moment the model stops asking for tools. `hit_step_limit` is traced
# so it is visible if this ceiling starts binding.
MAX_STEPS = 6

# Evidence budget per tool result. Aggregations get more room because they carry
# the record ids behind their number, which is what makes the answer citable.
EVIDENCE_CHARS = 1500
EVIDENCE_CHARS_COMPUTED = 4000

# Bump when the pipeline changes in a way that invalidates cached answers —
# prompts, tools, refusal rules. Without it a cached answer from the previous
# version silently replays the old system through every eval run after a change.
PIPELINE_VERSION = "2"

CACHE_FILE = Path(__file__).parent / ".answer_cache.json"
CACHE_ENABLED = os.environ.get("ANSWER_CACHE", "1") != "0"
_CACHE: dict[str, Answer] = {}


# ---------------------------------------------------------------------------
# Answer cache
# ---------------------------------------------------------------------------


def cache_key(question: str) -> str:
    """Normalised so case and spacing differences hit the same entry."""
    normalised = " ".join((question or "").lower().split())
    return hashlib.sha1(f"v{PIPELINE_VERSION}|{normalised}".encode()).hexdigest()


def _load_cache() -> None:
    if not CACHE_FILE.exists():
        return
    try:
        for key, value in json.loads(CACHE_FILE.read_text()).items():
            _CACHE[key] = Answer(**value)
    except (json.JSONDecodeError, TypeError, ValueError):
        _CACHE.clear()          # a stale or corrupt cache is not worth rescuing


def _save_cache() -> None:
    try:
        CACHE_FILE.write_text(
            json.dumps({k: v.model_dump() for k, v in _CACHE.items()}, indent=0))
    except OSError:
        pass


if CACHE_ENABLED:
    _load_cache()
    atexit.register(_save_cache)


# ---------------------------------------------------------------------------
# Stage 1 — gather evidence
# ---------------------------------------------------------------------------


def gather_evidence(question: str, trace: Optional[observability.Trace] = None
                    ) -> tuple[list[ToolCall], list[str]]:
    """Let the model call tools; run them; collect the real results.

    Returns (tool calls as executed, evidence lines).
    """
    messages = [
        {"role": "system", "content": GATHER_PROMPT},
        {"role": "user", "content": question},
    ]
    executed: list[ToolCall] = []
    evidence: list[str] = []
    finished = False
    forced = False

    for step in range(MAX_STEPS):
        response = completion(
            model=MODEL, messages=messages, tools=TOOL_SCHEMAS, tool_choice="auto")
        if trace is not None:
            trace.steps += 1
            observability.add_usage(trace, response)

        message = response.choices[0].message
        requested = getattr(message, "tool_calls", None) or []

        # An answer with no evidence behind it is the worst output this system
        # can produce: fluent, confident, and invented. Weaker models sometimes
        # answer a data question straight from the prompt on the first turn, so
        # if the very first turn asks for no tools, force one. Detectable in
        # code, so it is handled in code rather than left to the prompt holding.
        if not requested and step == 0 and not forced:
            forced = True
            retry = completion(model=MODEL, messages=messages,
                               tools=TOOL_SCHEMAS, tool_choice="required")
            if trace is not None:
                trace.steps += 1
                trace.forced_tool_use = True
                observability.add_usage(trace, retry)
            retried = getattr(retry.choices[0].message, "tool_calls", None) or []
            if retried:
                message, requested = retry.choices[0].message, retried

        # Re-add the assistant turn in canonical dict form, which is portable
        # across provider and litellm versions.
        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {"id": call.id, "type": "function",
                 "function": {"name": call.function.name,
                              "arguments": call.function.arguments}}
                for call in requested
            ],
        })

        if not requested:
            finished = True
            break

        for call in requested:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            function = REGISTRY.get(name)
            if function is None:
                result = {"error": f"unknown tool {name}"}
            else:
                try:
                    result = function(**args)
                except Exception as e:
                    # A bad argument should not kill a multi-step investigation.
                    # Feed the error back as a normal tool result and let the
                    # model correct itself inside the same loop.
                    result = {"error": f"{type(e).__name__}: {e}"}

            failed = isinstance(result, dict) and "error" in result
            executed.append(ToolCall(name=name, args=args, ok=not failed))
            if trace is not None:
                trace.tools_used.append(name)
                trace.tool_errors += int(failed)

            budget = EVIDENCE_CHARS_COMPUTED if name in COMPUTED_TOOLS else EVIDENCE_CHARS
            payload = json.dumps(result)[:budget]
            evidence.append(f"[{name}({args})] -> {payload}")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": payload})

    if trace is not None:
        trace.hit_step_limit = not finished

    return executed, evidence


# ---------------------------------------------------------------------------
# Stage 2 — turn evidence into a structured Answer
# ---------------------------------------------------------------------------


def compose_answer(question: str, evidence: list[str],
                   trace: Optional[observability.Trace] = None) -> Answer:
    """One structured-output call. Evidence in, Answer out."""
    body = "\n\n".join(evidence) if evidence else "(no tools were called)"
    prompt = ANSWER_PROMPT.format(question=question, evidence=body)

    client = instructor.from_litellm(completion)
    kwargs = dict(
        model=MODEL,
        response_model=Answer,
        messages=[{"role": "user", "content": prompt}],
        num_retries=4,
    )
    if trace is None:
        return client.chat.completions.create(**kwargs)
    try:
        # create_with_completion also returns the raw response, which is where
        # token usage lives. Falls back cleanly on versions without it.
        answer, raw = client.chat.completions.create_with_completion(**kwargs)
        observability.add_usage(trace, raw)
        return answer
    except AttributeError:
        return client.chat.completions.create(**kwargs)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def ask(question: str) -> Answer:
    """Answer one support question, grounded in tools and policy."""
    started = time.perf_counter()
    trace = observability.Trace(question=question, model=MODEL)

    key = cache_key(question) if CACHE_ENABLED else None
    if key is not None and key in _CACHE:
        hit = _CACHE[key]
        trace.cached = True
        trace.declined = hit.declined
        trace.n_sources = len(hit.sources)
        trace.answer_chars = len(hit.text or "")
        trace.tools_used = [t.name for t in hit.tool_calls]
        trace.total_ms = (time.perf_counter() - started) * 1000
        observability.record(trace)
        return hit.model_copy(deep=True)      # a copy, never the shared object

    try:
        mark = time.perf_counter()
        executed, evidence = gather_evidence(question, trace)
        trace.gather_ms = (time.perf_counter() - mark) * 1000

        mark = time.perf_counter()
        answer = compose_answer(question, evidence, trace)
        trace.answer_ms = (time.perf_counter() - mark) * 1000
    except Exception as e:
        trace.error = f"{type(e).__name__}: {e}"
        trace.total_ms = (time.perf_counter() - started) * 1000
        observability.record(trace)
        raise

    # What actually ran, not what the model says it ran.
    answer.tool_calls = executed

    # The outcome is decided in code where the right answer is enumerable, and
    # by the model's own structured field where it genuinely is not. There is no
    # second model call. See refusal.py.
    decision = refusal_policy.classify(
        question=question,
        answer_text=answer.text or "",
        model_declined=answer.declined,
        model_reason=answer.decline_reason,
        evidence=evidence,
    )
    answer.outcome = "declined" if decision.declined else "answered"
    answer.decline_reason = decision.reason

    trace.declined = decision.declined
    trace.decision_rule = decision.rule
    trace.decision_source = decision.source
    trace.n_sources = len(answer.sources)
    trace.bad_sources = len(answer.unrecognised_sources())
    trace.answer_chars = len(answer.text or "")
    trace.total_ms = (time.perf_counter() - started) * 1000
    observability.record(trace)

    if key is not None:
        _CACHE[key] = answer.model_copy(deep=True)

    return answer


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or (
        "An operator says case CS-8312 is handled. Is it actually still inside "
        "its response window, or did we miss it?")
    print(f"today: {TODAY}   model: {MODEL}\n")
    print(json.dumps(ask(prompt).model_dump(), indent=2))
