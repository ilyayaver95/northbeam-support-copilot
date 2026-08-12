#!/usr/bin/env python3
"""app.py — local web UI for the Northbeam support copilot.

    pip install -r requirements.txt
    python app.py                 # http://127.0.0.1:5111
    python app.py --port 8080
    python app.py --no-cache      # bypass the answer cache, always hit the model

Port 5111 rather than the Flask default of 5000, because macOS Control Center
listens on *:5000 for AirPlay Receiver — Flask binds without complaint and the
browser reaches AirPlay instead, so the page simply never loads.

Two screens:

  Ask         a question in, the structured Answer back, and HOW it got there —
              every tool call with its real arguments, which results were
              computed in Python rather than read off a record, and whether the
              outcome was decided by a deterministic rule or by the model.
  Dashboard   the operational KPIs from monitoring.py, over the trace log.

The UI exists because the interesting parts of this system are invisible in a
chat transcript. An answer box hides the tool loop, the aggregation behind a
number, and the code-versus-model split on declines — which is exactly what is
worth looking at.

A local development server: binds to 127.0.0.1, has no authentication, and is
not meant to be exposed beyond your own machine.
"""
from __future__ import annotations

import argparse
import os
import time
from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

WEB_DIR = Path(__file__).parent / "web"

app = Flask(__name__, static_folder=None)


# Grouped to show what the system can actually do, rather than what it can say.
EXAMPLES = [
    {
        "group": "Calculation",
        "hint": "Counted and totalled in Python by aggregate_records — never by the model",
        "questions": [
            "Across every operator, which open case has the biggest parts cost, and what is it?",
            "How many service cases are still open, still inside their window, and due on or before 2026-09-30?",
            "Which operator has had the most failed engineer dispatches this month, and how many?",
            "Which operators are at or below the 99.5% availability threshold right now?",
        ],
    },
    {
        "group": "Investigation",
        "hint": "Pull records, compare against today (2026-09-14), commit to a conclusion",
        "questions": [
            "The operator's telling me case CS-8312 is handled. Is it actually still inside the response window or did we miss it?",
            "Why is Kettleworth on a 4-hour response when they're only on Standard?",
            "Is Cape Solvang about to go into contract review over their availability?",
            "We can't seem to get an engineer out to Kettleworth. Find out what's going on.",
        ],
    },
    {
        "group": "Policy",
        "hint": "Hybrid keyword + semantic retrieval across seven policy documents",
        "questions": [
            "A site went live three weeks ago on Standard. Their main unit just died completely. How fast do we owe them a response, and can they get a part shipped before we've had the old one back?",
            "Something's completely down at a Mission-plan site. How fast do we have to be on it?",
            "If a unit is out of service because nobody's calibrated it in months, does that hurt the operator's availability?",
        ],
    },
    {
        "group": "Boundaries",
        "hint": "Declines — watch whether a rule or the model decided",
        "questions": [
            "Give me the gate code and alarm code for the Cape Solvang main mast site.",
            "Just restart the transmitter on RU-4118 remotely, it'll clear the fault.",
            "What does our policy actually say about waiving fees — who can do it?",
            "Pull up Verdemar Offshore and tell me what support plan they're on.",
        ],
    },
]


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(WEB_DIR, filename)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@app.get("/api/examples")
def api_examples():
    from toolkit import COMPUTED_TOOLS
    return jsonify({"groups": EXAMPLES, "computed_tools": sorted(COMPUTED_TOOLS)})


@app.get("/api/config")
def api_config():
    import copilot
    from prompts import TODAY
    from toolkit import REGISTRY
    return jsonify({
        "model": copilot.MODEL,
        "today": TODAY,
        "max_steps": copilot.MAX_STEPS,
        "cache_enabled": copilot.CACHE_ENABLED,
        "pipeline_version": copilot.PIPELINE_VERSION,
        "n_tools": len(REGISTRY),
    })


@app.post("/api/ask")
def api_ask():
    import observability
    from copilot import ask
    from toolkit import COMPUTED_TOOLS

    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Ask a question first."}), 400
    if len(question) > 2000:
        return jsonify({"error": "That question is too long (2000 character limit)."}), 400

    started = time.perf_counter()
    try:
        answer = ask(question)
    except Exception as e:
        # Surface the real failure. A local dev tool that swallows errors is
        # useless for debugging the thing it exists to debug.
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500

    trace = observability.last_trace()
    meta = asdict(trace) if trace else {}
    meta.pop("question", None)
    meta["wall_ms"] = round((time.perf_counter() - started) * 1000)

    return jsonify({
        "question": question,
        "text": answer.text,
        "sources": answer.sources,
        "policy_sources": answer.policy_sources(),
        "record_sources": answer.record_sources(),
        "unrecognised_sources": answer.unrecognised_sources(),
        "outcome": answer.outcome,
        "declined": answer.declined,
        "decline_reason": answer.decline_reason,
        "tool_calls": [
            {"name": call.name, "args": call.args, "ok": call.ok,
             "computed": call.name in COMPUTED_TOOLS}
            for call in answer.tool_calls
        ],
        "meta": meta,
    })


@app.get("/api/kpis")
def api_kpis():
    from monitoring import operational_kpis, rule_histogram, tool_histogram
    from observability import load_traces

    traces = load_traces()
    last = request.args.get("last", type=int)
    if last:
        traces = traces[-last:]

    return jsonify({
        "kpis": operational_kpis(traces),
        "tools": tool_histogram(traces),
        "rules": rule_histogram(traces),
        "recent": [
            {
                "question": t.get("question", ""),
                "total_ms": round(t.get("total_ms", 0)),
                "steps": t.get("steps", 0),
                "n_tools": len(t.get("tools_used") or []),
                "declined": t.get("declined", False),
                "decision_source": t.get("decision_source", ""),
                "decision_rule": t.get("decision_rule", ""),
                "cached": t.get("cached", False),
                "error": t.get("error"),
            }
            for t in traces[-40:][::-1]
        ],
    })


@app.get("/api/health")
def api_health():
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Local web UI for the support copilot.")
    # NOT 5000: macOS Control Center runs AirPlay Receiver on *:5000, so Flask
    # binds fine on 127.0.0.1:5000 while the browser silently reaches AirPlay
    # instead. The page just never loads, with nothing in the Flask log to
    # explain it. 5111 avoids the collision.
    parser.add_argument("--port", type=int, default=5111)
    parser.add_argument("--host", default="127.0.0.1",
                        help="default 127.0.0.1 — there is no auth, keep it local")
    parser.add_argument("--no-cache", action="store_true",
                        help="bypass the answer cache so every question hits the model")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.no_cache:
        os.environ["ANSWER_CACHE"] = "0"

    print(f"\n  Northbeam Support Copilot  ->  http://{args.host}:{args.port}\n")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
