"""refusal.py — deciding "did we decline?" in code.

The obvious way to build this is a second model call that reads the question and
the answer and judges whether the copilot refused. That is what this replaces.
It cost an extra round trip per question, it was non-deterministic, and it was
guessing at something the system already had enough information to know.

The rule applied here, and throughout the system:

    if the right answer is enumerable  -> code
    if it genuinely depends on context -> model, and measure it

Which lands as:

  code   | the request names something Northbeam never exposes — site access
         | credentials, staff home addresses, API keys, raw signal recordings.
         | A closed list. It does not vary with context, so it should not vary
         | with a sample.
  code   | the request is an imperative to CHANGE something. The copilot has
         | only read tools, so this is a capability fact, not a judgement.
  code   | a tool reported that a record the question named does not exist.
         | "There is no such unit" is an ANSWER, however the model phrased it.
  model  | everything else — whose data it is, whether a question is really
         | asking for regulatory advice, whether a value is knowable. These
         | need context the rules cannot see, so the model's own structured
         | `outcome` from the single answer call stands.
  code   | the invariants either way: a decline always carries a reason, an
         | answer never does.

Every decision reports which rule fired and whether code or the model made it,
so the split is visible in the trace instead of assumed.

Pure functions. No I/O, no network, no model. Unit-testable without an API key.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Decision:
    declined: bool
    reason: Optional[str]
    rule: str            # which rule decided, recorded on the trace
    source: str          # "code" | "model"


# ---------------------------------------------------------------------------
# Rule 1 — values Northbeam never discloses
# ---------------------------------------------------------------------------

# High precision by construction. Each pattern names something that is out of
# bounds in every context, so no amount of surrounding phrasing makes it fine.
PROTECTED_PATTERNS: list[tuple[str, str]] = [
    (r"\b(gate|alarm|door|access|entry)\s*(code|codes|combination)s?\b"
     r"|\bkey[- ]?safe\b"
     r"|\bsite\s+(vpn|access)\s+(credential|password|login)s?\b",
     "Site access credentials are held by the operator, not by Northbeam. "
     "Engineers are issued them per visit and they are not retained."),

    (r"\b(home|personal|private)\s+(address|addresses|phone|mobile|number)\b"
     r"|\b(passport|identity document|id number|national insurance|social security)\b"
     r"|\bpersonal (details|contact details) (of|for) (the )?(site |field )?(staff|engineer|contact)\b",
     "Northbeam does not hold personal details for site staff — only a name and "
     "a work address inside the operator's own portal tenant."),

    (r"\bnbk_live_|\b(api|access)\s+key\b.{0,40}\b(give|show|read|retrieve|send|what is|reset|generate|create)\b"
     r"|\b(give|show|read|retrieve|send|generate|create|reset)\b.{0,40}\b(api|access)\s+key\b",
     "API keys are stored only as a hash and cannot be read back by anyone, "
     "including Northbeam. The operator's own portal administrator rotates them."),

    (r"\b(raw )?(iq|i/q)\s+(data|recording|recordings)\b"
     r"|\braw signal recording"
     r"|\b(track|tracked|detections?) (of|for) (the )?(vessel|vessels|aircraft|ship|ships)\b"
     r"|\b(vessel|aircraft) (tracks|positions)\b",
     "Raw signal recordings are deleted on a rolling 72-hour window and are never "
     "exposed. The detections a unit produces belong to the operator and never "
     "reach Northbeam's systems."),
]

_PROTECTED = [(re.compile(p, re.I), reason) for p, reason in PROTECTED_PATTERNS]

# Asking what Northbeam holds, or how long it holds it for, is a POLICY question
# and always answerable — "how long do we keep the raw recordings" is ordinary
# support work, while "send me the recording from RU-4118" is not. The patterns
# above match the noun, so without this guard they would swallow the policy
# question too, which is the over-declining failure this system cares most about.
_CATEGORY_QUESTION_RE = re.compile(
    r"\b(?:what|which|how much|how long|how many|do|does|are|is|can)\b[^?]{0,80}?"
    r"\b(?:hold|holds|store|stores|stored|keep|keeps|kept|retain|retains|retained|"
    r"log|logged|record|recorded|expose|exposed|have on file|on file)\b"
    r"|\bpolicy\b[^?]{0,40}\b(?:on|about|for|say)\b"
    r"|\bhow (?:do|does|would|can)\b[^?]{0,60}\b(?:reset|rotate|issue|request|obtain|get)\b"
    r"|\bwalk me through\b|\btalk me through\b|\bexplain\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Rule 2 — imperatives that would change state
# ---------------------------------------------------------------------------

# Filler that can precede an imperative without changing that it is one.
_FILLER = (
    r"(?:please\s+|just\s+|now\s+|go ahead and\s+|can you\s+|could you\s+|"
    r"i need you to\s+|i want you to\s+|you need to\s+|"
    r"i'?m authoris(?:e|ing) you to\s+|i'?m authoriz(?:e|ing) you to\s+|"
    r"as an admin,?\s+|as the account director,?\s+)*"
)

# Verbs that mutate a unit, a case, an account, money, or a control. The copilot
# has only read tools, so any of these as an imperative is out of scope as a
# matter of capability rather than judgement.
#
# Read verbs (show, pull, list, get, look up, find, check, read, open) and
# compose verbs (draft, write, explain, summarise) are deliberately absent —
# those are legitimate requests whose answer depends on context.
_ACTION_VERBS = (
    r"restart|reboot|reset|power[- ]?cycle|reconfigure|recalibrate|"
    r"silence|suppress|mute|disable|turn off|shut off|deactivate|"
    r"waive|credit|refund|discount|write[- ]off|"
    r"extend|renew|cancel|close|resolve|reopen|"
    r"suspend|reinstate|unblock|whitelist|"
    r"override|change|set|adjust|lower|raise|increase|decrease|bump|"
    r"mark|approve|deny|reject|escalate|dispatch|"
    r"issue|revoke|rotate|provision|delete|remove"
)

_ACTION_RE = re.compile(rf"(?:^|[.;!?]\s+|\band\s+){_FILLER}(?:{_ACTION_VERBS})\b", re.I)

# Requiring one of these alongside the verb keeps precision high — it is what
# separates "reset the alarm threshold" from an incidental use of the word. A
# bare record id counts as an object on its own: "reboot RU-4118" names its
# target more precisely than any noun could.
_ACTION_OBJECT_RE = re.compile(
    r"\b(?:OP|RU|CS|TKT)-\d{2,6}\b"
    r"|\b(unit|units|radar|transmitter|receiver|mast|array|radome|antenna|"
    r"module|board|psu|pedestal|"
    r"case|cases|operator|operators|account|accounts|site|sites|"
    r"alarm|alarms|alert|alerts|threshold|thresholds|calibration|"
    r"credit|credits|fee|fees|invoice|invoices|warranty|warranties|"
    r"severity|sla|deadline|window|windows|deposit|dispatch|engineer|"
    r"firmware|key|keys|user|users|permission|permissions|status|flag|flags)\b",
    re.I,
)

# An inform or compose framing at the START of the request means the engineer is
# asking about an action, not for one. Checked before the action rule.
_INFORM_RE = re.compile(
    r"^(?:\s*)(what|what's|whats|how|why|when|which|who|where|is|are|was|were|"
    r"does|do|did|can|could|should|would|will|"
    r"explain|describe|clarify|draft|write|compose|summar|walk|outline|confirm whether|"
    r"tell me (?:what|how|why|about|whether)|"
    r"pull|look up|show|list|get me|find|check|read|open|review)\b",
    re.I,
)


def _is_inform_request(question: str) -> bool:
    return bool(_INFORM_RE.match((question or "").strip()))


def protected_value_reason(question: str) -> Optional[str]:
    """Reason this request names something Northbeam never discloses, or None.

    Returns None for policy questions ABOUT those things — see
    `_CATEGORY_QUESTION_RE`.
    """
    question = question or ""
    if _CATEGORY_QUESTION_RE.search(question):
        return None
    for pattern, reason in _PROTECTED:
        if pattern.search(question):
            return reason
    return None


def state_change_reason(question: str) -> Optional[str]:
    """Reason this request is an imperative to change something, or None."""
    if _is_inform_request(question):
        return None
    match = _ACTION_RE.search(question or "")
    if not match or not _ACTION_OBJECT_RE.search(question or ""):
        return None
    verb = match.group(0).strip().split()[-1].lower()
    return (
        f"This copilot has read-only access and cannot {verb} anything on a unit, "
        "case or account. That has to go through the team that owns the action."
    )


# ---------------------------------------------------------------------------
# Rule 3 — a missing record is an answer, not a decline
# ---------------------------------------------------------------------------

_NOT_FOUND_RE = re.compile(r"\"error\"\s*:\s*\"[^\"]*(not found|no operator matching)", re.I)

# Record ids as they appear in questions and in tool arguments.
_RECORD_ID_RE = re.compile(r"\b(?:OP|RU|CS|TKT|EV)-\d{2,6}\b", re.I)


def evidence_reports_missing_record(evidence: list[str], question: str = "") -> bool:
    """True when a tool reported that a record the QUESTION named does not exist.

    The id coupling is what keeps this rule honest. An earlier version fired on
    any not-found anywhere in the evidence, which meant one stray failed lookup
    during a genuinely refusable request could launder the decline into an
    answer. The missing record now has to be one the engineer actually asked
    about — the only case where "there is no such record" answers their question.

    With no id in the question, nothing can be confirmed missing, so this returns
    False and the decision falls through to the model.
    """
    hits = [line for line in evidence if _NOT_FOUND_RE.search(line)]
    if not hits:
        return False
    asked_about = {m.upper() for m in _RECORD_ID_RE.findall(question or "")}
    if not asked_about:
        return False
    return any(asked_about & {m.upper() for m in _RECORD_ID_RE.findall(line)}
               for line in hits)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def classify(
    question: str,
    answer_text: str = "",
    model_declined: bool = False,
    model_reason: Optional[str] = None,
    evidence: Optional[list[str]] = None,
) -> Decision:
    """Decide the final outcome. Deterministic given its inputs.

    Args:
        question: what the support engineer asked.
        answer_text: the prose the system produced.
        model_declined: the `outcome` from the single structured answer call,
                        as a boolean.
        model_reason: `decline_reason` from that same call.
        evidence: tool-result lines from the loop, used to spot missing records.

    Returns:
        Decision(declined, reason, rule, source).
    """
    question = question or ""
    evidence = evidence or []

    # Rule 1 outranks everything: a request that also asks for a gate code is a
    # decline even if the rest of it was answerable.
    reason = protected_value_reason(question)
    if reason:
        return Decision(True, reason, "protected_value", "code")

    reason = state_change_reason(question)
    if reason:
        return Decision(True, reason, "state_change_action", "code")

    # Rule 3 only ever flips toward answering, and only for a record the question
    # named. It cannot rescue anything rules 1 and 2 already caught.
    if model_declined and evidence_reports_missing_record(evidence, question):
        return Decision(False, None, "missing_record_is_an_answer", "code")

    # Genuinely contextual. The model's own structured outcome stands — there is
    # no second call to second-guess it.
    if model_declined:
        return Decision(
            True,
            (model_reason or "").strip() or "Outside what this copilot can provide.",
            "model_judgment",
            "model",
        )
    return Decision(False, None, "model_judgment", "model")
