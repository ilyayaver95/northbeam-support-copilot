#!/usr/bin/env python3
"""run_all.py — every suite, one score table, one comparable run record.

    python -m evals.run_all                        # run everything
    python -m evals.run_all --samples 3            # majority-of-3 per case
    python -m evals.run_all --verbose              # list each failing case
    python -m evals.run_all --save after.json      # write a run record

A saved run is the unit of version comparison. It carries the git sha, the
model, per-category scores, the failing case ids, and the behavioural KPIs
below — enough to answer "did this change help?" without re-running the old
version:

    python -m evals.run_all --save before.json
    ...change something...
    python -m evals.run_all --save after.json
    python monitoring.py compare before.json after.json    # exits 1 on regression

Exit code is the number of failing cases, so it gates in CI unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from .grader import Case, HEDGES, Result
from .runner import SUITES, load_suite, print_results, run_suite


def behaviour_kpis(cases: list[Case], results: list[Result]) -> dict:
    """How it was wrong, not just how often.

    The pass rate says whether the system was right. These say which way it
    failed, which is what tells you where the next change should go:

      over_decline   refused something it was supposed to answer. The most
                     damaging failure for a support tool — it looks safe.
      under_decline  answered something it should have refused. The most
                     damaging for risk.
      hedge          vague prose where a committed fact was expected.
      citation_cov   answered cases that cite at least one source.
      tool_cov       answers grounded in at least one real tool result.
      bad_citation   cited something matching no known id shape — a fabricated
                     source, which substring grading alone would never catch.
    """
    by_id = {c.id: c for c in cases}
    over = over_total = under = under_total = 0
    hedged = cited = cited_total = tooled = bad_cites = graded = 0

    for result in results:
        answer = getattr(result, "answer", None)
        case = by_id.get(result.case_id)
        if answer is None or case is None:
            continue
        graded += 1

        declined = bool(getattr(answer, "declined", False))
        text = (getattr(answer, "text", "") or "").lower()

        if case.expect_declined is False:
            over_total += 1
            over += declined
        elif case.expect_declined is True:
            under_total += 1
            under += not declined

        if any(h in text for h in HEDGES):
            hedged += 1
        if not declined:
            cited_total += 1
            cited += bool(getattr(answer, "sources", None))
        tooled += bool(getattr(answer, "tool_calls", None))

        unrecognised = getattr(answer, "unrecognised_sources", None)
        if callable(unrecognised) and unrecognised():
            bad_cites += 1

    def rate(n: int, d: int) -> float:
        return round(100.0 * n / d, 1) if d else 0.0

    return {
        "graded": graded,
        "over_decline_pct": rate(over, over_total),
        "under_decline_pct": rate(under, under_total),
        "hedge_pct": rate(hedged, graded),
        "citation_coverage_pct": rate(cited, cited_total),
        "tool_coverage_pct": rate(tooled, graded),
        "bad_citation_pct": rate(bad_cites, graded),
    }


def colours(enabled: bool):
    if not enabled:
        return "", "", "", ""
    return "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run every eval suite and summarise.")
    parser.add_argument("--samples", type=int, default=1,
                        help="run each case N times, take the majority verdict")
    parser.add_argument("--verbose", action="store_true",
                        help="print per-case PASS/FAIL lines too")
    parser.add_argument("--save", metavar="FILE", default=None,
                        help="write this run's record to a JSON file")
    parser.add_argument("--baseline", metavar="FILE", default=None,
                        help="show a delta column against a previously saved run")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args(argv)

    from copilot import ask          # late import so --help needs no API key

    use_colour = (not args.no_color) and sys.stdout.isatty()
    GREEN, RED, DIM, RESET = colours(use_colour)

    baseline = {}
    if args.baseline:
        try:
            baseline = json.loads(Path(args.baseline).read_text()).get("scores", {})
        except FileNotFoundError:
            print(f"(baseline {args.baseline!r} not found — no delta column)\n",
                  file=sys.stderr)

    scores: dict[str, dict] = {}
    every_case: list[Case] = []
    every_result: list[Result] = []
    failing: list[str] = []
    total_passed = total_cases = 0
    started = time.time()

    for suite in SUITES:
        cases = load_suite(suite)
        results = run_suite(cases, ask, samples=max(1, args.samples))
        if args.verbose:
            print(f"\n===== {suite} =====")
            print_results(cases, results)

        passed = sum(1 for r in results if r.passed)
        scores[suite] = {"passed": passed, "total": len(results)}
        failing.extend(r.case_id for r in results if not r.passed)
        every_case.extend(cases)
        every_result.extend(results)
        total_passed += passed
        total_cases += len(results)

    elapsed = time.time() - started
    behaviour = behaviour_kpis(every_case, every_result)

    show_delta = bool(baseline)
    width = 58 + (10 if show_delta else 0)
    print("\n" + "=" * width)
    print(f"  SCORES   (samples={args.samples})")
    print("=" * width)
    header = f"  {'category':<24}{'passed':>8}{'pct':>7}"
    if show_delta:
        header += f"{'delta':>12}"
    print(header)
    print("  " + "-" * (width - 4))

    for category, score in scores.items():
        passed, total = score["passed"], score["total"]
        percent = 100 * passed / total if total else 0
        tint = GREEN if passed == total else (RED if passed == 0 else "")
        line = f"  {category:<24}{tint}{passed:>4}/{total:<3}{RESET}{percent:>6.0f}%"
        if show_delta:
            before = baseline.get(category, {})
            if before.get("total"):
                delta = passed - before["passed"]
                shown = f"+{delta}" if delta > 0 else str(delta)
                tone = GREEN if delta > 0 else (RED if delta < 0 else DIM)
                line += f"{tone}{shown:>12}{RESET}"
            else:
                line += f"{DIM}{'—':>12}{RESET}"
        print(line)

    print("  " + "-" * (width - 4))
    overall = 100 * total_passed / total_cases if total_cases else 0
    tint = GREEN if total_passed == total_cases else ""
    print(f"  {'TOTAL':<24}{tint}{total_passed:>4}/{total_cases:<3}{RESET}{overall:>6.0f}%")
    print(f"\n  {DIM}{total_cases} cases in {elapsed:.1f}s{RESET}")

    print("\n  behaviour")
    print(f"  {DIM}{'-' * 54}{RESET}")
    for label, key in [
        ("over-decline (refused an answerable)", "over_decline_pct"),
        ("under-decline (answered a refusal)", "under_decline_pct"),
        ("hedge rate", "hedge_pct"),
        ("citation coverage", "citation_coverage_pct"),
        ("tool coverage", "tool_coverage_pct"),
        ("malformed citations", "bad_citation_pct"),
    ]:
        print(f"  {label:<42}{behaviour[key]:>6.1f}%")

    if args.save:
        import observability
        Path(args.save).write_text(json.dumps({
            "timestamp": time.time(),
            "version": observability.system_version(),
            "sha": observability.git_sha(),
            "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
            "samples": args.samples,
            "elapsed_s": round(elapsed, 1),
            "scores": scores,
            "behaviour": behaviour,
            "failing_case_ids": failing,
        }, indent=2))
        print(f"\n  saved -> {args.save}")
        print(f"  compare: python monitoring.py compare <baseline.json> {args.save}")

    return total_cases - total_passed


if __name__ == "__main__":
    raise SystemExit(main())
