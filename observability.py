"""observability.py — one structured trace per answered question.

Without this the system is a black box. You can see whether an eval passed, but
not why it got slower, which tools it burned steps on, how often the loop hit its
ceiling, or whether a decline came from a rule or from the model. Every KPI in
`monitoring.py` is computed from the JSONL this writes.

Three choices worth naming:

  Append-only JSONL. Greppable, loadable in one line, no service to run. The
  right answer at a real scale is a hosted tracing platform; the right answer
  here is a file.

  Never raises into the caller. Telemetry that can break the product is worse
  than no telemetry, so every write is guarded.

  Records a stable question id alongside the text, so the same question can be
  joined across versions to see whether a change helped it specifically.

Environment:
    TRACE_LOG=0            turn tracing off
    TRACE_LOG_PATH=<file>  override traces/traces.jsonl
    SYSTEM_VERSION=<str>   tag traces with a version label for A/B comparison
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

DEFAULT_PATH = Path(__file__).parent / "traces" / "traces.jsonl"


def tracing_enabled() -> bool:
    return os.environ.get("TRACE_LOG", "1") != "0"


def trace_path() -> Path:
    return Path(os.environ.get("TRACE_LOG_PATH", str(DEFAULT_PATH)))


_git_sha: Optional[str] = None


def git_sha() -> str:
    """Short commit sha, so a trace ties back to the code that produced it."""
    global _git_sha
    if _git_sha is None:
        try:
            _git_sha = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=Path(__file__).parent, stderr=subprocess.DEVNULL, text=True,
            ).strip()
        except Exception:
            _git_sha = "unknown"
    return _git_sha


def system_version() -> str:
    """Version label for A/B comparison. Defaults to the git sha."""
    return os.environ.get("SYSTEM_VERSION") or git_sha()


def question_id(question: str) -> str:
    normalised = " ".join((question or "").lower().split())
    return hashlib.sha1(normalised.encode()).hexdigest()[:12]


@dataclass
class Trace:
    """Everything worth knowing about one answered question."""

    question: str
    qid: str = ""
    version: str = field(default_factory=system_version)
    sha: str = field(default_factory=git_sha)
    model: str = ""
    timestamp: float = field(default_factory=time.time)

    # latency
    total_ms: float = 0.0
    gather_ms: float = 0.0
    answer_ms: float = 0.0

    # the loop
    steps: int = 0                     # model turns inside the tool loop
    hit_step_limit: bool = False       # ran out of steps before the model stopped
    forced_tool_use: bool = False      # first turn wanted to answer with no evidence
    tools_used: list[str] = field(default_factory=list)
    tool_errors: int = 0

    # the output
    declined: bool = False
    decision_rule: str = ""            # which rule decided; see refusal.py
    decision_source: str = ""          # "code" | "model"
    n_sources: int = 0
    bad_sources: int = 0               # citations matching no known id shape
    answer_chars: int = 0

    # cost
    prompt_tokens: int = 0
    completion_tokens: int = 0

    # reliability
    cached: bool = False
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.qid:
            self.qid = question_id(self.question)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


_last: Optional[Trace] = None


def last_trace() -> Optional[Trace]:
    """The most recently recorded trace.

    Lets an in-process caller (the local web UI) show how an answer was produced
    without re-reading the log. Single-process convenience only — the JSONL file
    stays the source of truth for anything aggregate.
    """
    return _last


def record(trace: Trace) -> None:
    """Append one trace. Does nothing if tracing is off or the write fails."""
    global _last
    _last = trace
    if not tracing_enabled():
        return
    try:
        path = trace_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as handle:
            handle.write(json.dumps(asdict(trace)) + "\n")
    except Exception:
        pass          # telemetry must never break the answer path


def load_traces(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Read every trace back. Skips malformed lines rather than failing."""
    resolved = Path(path) if path else trace_path()
    if not resolved.exists():
        return []
    out = []
    for line in resolved.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def add_usage(trace: Trace, response: Any) -> None:
    """Accumulate token usage off a response, whatever shape it arrives in."""
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if usage is None:
        return
    read = usage.get if isinstance(usage, dict) else (lambda k, d=0: getattr(usage, k, d))
    try:
        trace.prompt_tokens += int(read("prompt_tokens", 0) or 0)
        trace.completion_tokens += int(read("completion_tokens", 0) or 0)
    except (TypeError, ValueError):
        pass
