"""runner.py — load a suite, run it through `ask`, grade, print.

    python -m evals.runner investigation
    python -m evals.runner boundaries --verbose        # show every failed check
    python -m evals.runner tool_use --limit 3          # first N cases
    python -m evals.runner investigation --ids 001,004  # id suffixes
    python -m evals.runner honesty --samples 3         # majority of 3 runs

Exit code is the number of failures, so it gates in CI unchanged.
"""
from __future__ import annotations

import argparse
import importlib
import sys
from typing import Callable

from .grader import Case, Check, Result, grade

SUITES = ["policy_lookup", "synthesis", "tool_use",
          "investigation", "honesty", "boundaries"]


def load_suite(name: str) -> list[Case]:
    try:
        module = importlib.import_module(f"evals.suites.{name}")
    except ImportError as e:
        raise SystemExit(f"no suite named {name!r} ({e}). "
                         f"Available: {', '.join(SUITES)}")
    cases = getattr(module, "CASES", None)
    if cases is None:
        raise SystemExit(f"evals.suites.{name} defines no CASES list")
    return cases


def filter_cases(cases: list[Case], limit: int | None,
                 ids: list[str] | None) -> list[Case]:
    if ids:
        cases = [c for c in cases if any(c.id.endswith(i) for i in ids)]
    if limit:
        cases = cases[:limit]
    return cases


def grade_once(case: Case, ask: Callable[[str], object]) -> Result:
    try:
        return grade(case, ask(case.question))
    except Exception as e:
        return Result(case_id=case.id, passed=False,
                      checks=[Check("system_error", False,
                                    detail=f"{type(e).__name__}: {e}")])


def run_suite(cases: list[Case], ask: Callable[[str], object],
              samples: int = 1) -> list[Result]:
    """Grade every case.

    With samples > 1 each case runs N times and takes the MAJORITY verdict — a
    strict majority, ties counting as failure. This is for models that only run
    at temperature 1, where a single run is not reproducible. Majority vote gives
    an honest stable verdict; best-of-N would just inflate the score.
    """
    results: list[Result] = []
    for case in cases:
        if samples <= 1:
            results.append(grade_once(case, ask))
            continue

        runs = [grade_once(case, ask) for _ in range(samples)]
        passes = sum(1 for r in runs if r.passed)
        verdict = passes * 2 > samples

        # Show a run that agrees with the final verdict, so the printed failure
        # detail matches the reported outcome.
        representative = next((r for r in runs if r.passed == verdict), runs[-1])
        checks = [Check("samples", verdict, detail=f"{passes}/{samples} runs passed")]
        checks.extend(representative.checks)
        results.append(Result(case_id=case.id, passed=verdict, checks=checks,
                              answer=representative.answer))
    return results


def print_results(cases: list[Case], results: list[Result],
                  verbose: bool = False) -> None:
    by_id = {c.id: c for c in cases}
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        case = by_id.get(result.case_id)
        note = next((f"  [{c.detail}]" for c in result.checks if c.name == "samples"), "")
        print(f"[{status}] {result.case_id}{note}  {case.question if case else ''!r}")
        if verbose or not result.passed:
            for check in result.failures:
                detail = f"  ({check.detail})" if check.detail else ""
                print(f"        x {check.name}{detail}")

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{passed}/{total} passed ({100 * passed / total if total else 0:.0f}%)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", help=f"one of: {', '.join(SUITES)}")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--ids", type=str, default=None,
                        help="comma-separated case-id suffixes")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--samples", type=int, default=1,
                        help="run each case N times, take the majority verdict")
    args = parser.parse_args(argv)

    cases = filter_cases(load_suite(args.suite), args.limit,
                         args.ids.split(",") if args.ids else None)
    if not cases:
        print("No cases matched.", file=sys.stderr)
        return 0

    from copilot import ask          # imported late so --help needs no API key
    results = run_suite(cases, ask, samples=max(1, args.samples))
    print_results(cases, results, verbose=args.verbose)
    return sum(1 for r in results if not r.passed)


if __name__ == "__main__":
    raise SystemExit(main())
