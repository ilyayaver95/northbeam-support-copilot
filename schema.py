"""schema.py — the answer contract.

`ask()` returns an `Answer`, and everything downstream — the grader, the web UI,
the trace — reads it. Kept in its own module so nothing has to import the whole
pipeline just to construct or inspect one.

Two decisions worth naming:

  `outcome` is an enum, not a boolean. "Did it refuse?" turns out to have more
  than two useful states over time (declined, escalated, partially answered), and
  an enum extends where `refused: bool` would need a migration. It also reads
  better at the call site: `answer.outcome == "declined"`.

  `sources` is a flat list the model fills, and the policy/record split is
  DERIVED in code from the id shape. Asking the model to label each citation
  would be one more thing for it to get wrong, when a regex over "ends in .md"
  is exact. Same principle as the rest of the system: if the right answer is
  knowable, don't sample it.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

Outcome = Literal["answered", "declined"]

# Record ids across the domain: OP-2742, RU-4118, CS-8312, TKT-3108, EV-0042.
RECORD_ID = re.compile(r"^(OP|RU|CS|TKT|EV)-\d+$", re.I)


class ToolCall(BaseModel):
    """One tool invocation, as actually executed.

    Never self-reported: the loop overwrites this list with what it really ran,
    so a model that claims a lookup it never made cannot make it true.
    """

    name: str
    args: dict = Field(default_factory=dict)
    ok: bool = Field(
        default=True,
        description="False when the tool returned an error — a bad id, bad "
                    "arguments, or a record that does not exist.",
    )


class Answer(BaseModel):
    """What the copilot hands back for one question."""

    text: str = Field(
        description="The answer for the support engineer. Commit to a "
                    "conclusion; state what is missing as a fact, never as a hedge.",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Everything the answer rests on: policy document filenames "
                    "exactly as returned by search_policies (e.g. "
                    "'service_levels.md') and/or record ids relied on (e.g. "
                    "'CS-8312', 'OP-2742', 'RU-4118').",
    )
    outcome: Outcome = Field(
        default="answered",
        description="'declined' only when refusing to comply — the request is "
                    "out of scope, crosses a privacy or security boundary, or "
                    "asks for an action this copilot has no tool for. Reporting "
                    "that a record does not exist is 'answered', not 'declined'.",
    )
    decline_reason: Optional[str] = Field(
        default=None,
        description="Why the request was declined, and where it should go "
                    "instead. Set only when outcome is 'declined'.",
    )
    tool_calls: list[ToolCall] = Field(
        default_factory=list,
        description="Populated by the system from what actually ran.",
    )

    # -- derived views; all computed in code, never asked of the model --------

    @property
    def declined(self) -> bool:
        return self.outcome == "declined"

    def policy_sources(self) -> list[str]:
        """Cited policy documents."""
        return [s for s in self.sources if s.lower().endswith(".md")]

    def record_sources(self) -> list[str]:
        """Cited record ids."""
        return [s for s in self.sources if RECORD_ID.match(s.strip())]

    def unrecognised_sources(self) -> list[str]:
        """Citations that are neither a policy file nor a well-formed record id.

        Surfaced rather than silently dropped: a fabricated citation is a
        hallucination worth seeing, not tidying away.
        """
        known = set(self.policy_sources()) | set(self.record_sources())
        return [s for s in self.sources if s not in known]
