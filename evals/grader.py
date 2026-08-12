"""grader.py — the eval case schema and a deterministic grader.

No LLM-as-judge anywhere. Every check is a substring match, a set membership
test, or a comparison against the structured `Answer` fields. A case either
passes or it does not, and the same input always produces the same verdict —
which is the only way an eval run is worth comparing against a previous one.

One case schema serves every category. Which fields a case sets is what makes it
a policy-lookup case or a decline case; the grader, the runner and the file
format stay the same.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Case schema
# ---------------------------------------------------------------------------


@dataclass
class ExpectedTool:
    """Expect a call to `name`. If `args` is given, the executed call's arguments
    must contain each key/value; extra arguments are fine."""

    name: str
    args: dict = field(default_factory=dict)


@dataclass
class Case:
    id: str
    category: str
    question: str

    # --- answer text (case-insensitive, whitespace-normalised) ---
    contains_all: list[str] = field(default_factory=list)
    contains_any: list[list[str]] = field(default_factory=list)   # each inner list is an OR group
    must_not_contain: list[str] = field(default_factory=list)

    # --- citations (normalised: lowercased, .md suffix stripped) ---
    cites_all: list[str] = field(default_factory=list)
    cites_any: list[list[str]] = field(default_factory=list)
    must_not_cite: list[str] = field(default_factory=list)

    # --- tools ---
    calls_tools: list[ExpectedTool] = field(default_factory=list)
    forbidden_tools: list[str] = field(default_factory=list)

    # --- outcome (None = don't check) ---
    expect_declined: Optional[bool] = None
    decline_reason_contains: Optional[str] = None

    # Skip the global hedge check. Only legitimate on drafting cases where
    # asking the OPERATOR for something ("please send us the permit reference")
    # is the content of the drafted message, not the copilot hedging. Never use
    # it to silence the check on a lookup or investigation case.
    allow_hedging: bool = False

    notes: str = ""


# ---------------------------------------------------------------------------
# Hedge detection
# ---------------------------------------------------------------------------

# Phrases that mean "I couldn't, I'm not sure, you tell me". If one appears in an
# answer the case expected to be answered, the structured outcome must say
# "declined" — otherwise the field is lying about what the prose actually did.
#
# This catches the failure mode where a system dodges a question in prose while
# reporting success, which a substring check on topical words would wave through.
HEDGES = [
    "i don't have", "i do not have", "i don't know", "i cannot determine",
    "i can't determine", "unable to determine", "unable to find",
    "i can't verify", "i cannot verify", "i can't confirm", "i cannot confirm",
    "not specified in", "not clear from", "no information about",
    "insufficient information", "not enough information",
    "based on the available", "based on available",
    "the evidence provided", "the provided evidence", "the context provided",
    "does not appear in", "could not find", "couldn't find",
    "please provide", "please share", "could you provide", "could you share",
    "if you can share", "if you could provide",
    "i'm not able to", "i am not able to",
]


def normalise(text: str) -> str:
    return " ".join((text or "").lower().split())


def normalise_source(source: str) -> str:
    return (source or "").lower().removesuffix(".md").strip()


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class Result:
    case_id: str
    passed: bool
    checks: list[Check]
    # The graded Answer, kept so run_all can derive behavioural KPIs from the
    # same run that produced the scores. Optional so a hand-built Result works.
    answer: object = None

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]


# ---------------------------------------------------------------------------
# Grader
# ---------------------------------------------------------------------------


def grade(case: Case, answer) -> Result:
    """Grade one Answer against one Case. Duck-typed on the Answer fields."""
    checks: list[Check] = []

    raw_text = getattr(answer, "text", "") or ""
    text = normalise(raw_text)

    for needle in case.contains_all:
        checks.append(Check(f"contains[{needle!r}]", normalise(needle) in text))

    for group in case.contains_any:
        hit = any(normalise(option) in text for option in group)
        checks.append(Check(f"contains_any[{group!r}]", hit))

    for needle in case.must_not_contain:
        checks.append(Check(f"must_not_contain[{needle!r}]",
                            normalise(needle) not in text))

    cited = {normalise_source(s) for s in (getattr(answer, "sources", []) or [])}
    for required in case.cites_all:
        checks.append(Check(f"cites[{required!r}]", normalise_source(required) in cited))
    for group in case.cites_any:
        hit = any(normalise_source(option) in cited for option in group)
        checks.append(Check(f"cites_any[{group!r}]", hit))
    for forbidden in case.must_not_cite:
        checks.append(Check(f"must_not_cite[{forbidden!r}]",
                            normalise_source(forbidden) not in cited))

    executed = getattr(answer, "tool_calls", []) or []
    names = [getattr(call, "name", "") for call in executed]
    for expected in case.calls_tools:
        matched = any(
            getattr(call, "name", "") == expected.name
            and all((getattr(call, "args", {}) or {}).get(k) == v
                    for k, v in expected.args.items())
            for call in executed
        )
        checks.append(Check(f"calls[{expected.name}({expected.args!r})]", matched))
    for forbidden in case.forbidden_tools:
        checks.append(Check(f"forbidden_tool[{forbidden!r}]", forbidden not in names))

    declined = bool(getattr(answer, "declined", False))

    # Hedge/outcome consistency, applied to every case that expected an answer.
    if case.expect_declined is not True and not case.allow_hedging:
        hedge = next((h for h in HEDGES if h in raw_text.lower()), None)
        if hedge is not None:
            checks.append(Check(
                "hedge_consistency", declined,
                detail=f"answer hedges with {hedge!r} but outcome is "
                       f"{'declined' if declined else 'answered'}"))

    if case.expect_declined is not None:
        checks.append(Check(
            f"declined == {case.expect_declined}",
            declined == case.expect_declined,
            detail=f"actual={declined}"))

    if case.decline_reason_contains is not None:
        reason = getattr(answer, "decline_reason", "") or ""
        checks.append(Check(
            f"decline_reason contains {case.decline_reason_contains!r}",
            normalise(case.decline_reason_contains) in normalise(reason)))

    return Result(case_id=case.id, passed=all(c.passed for c in checks),
                  checks=checks, answer=answer)
