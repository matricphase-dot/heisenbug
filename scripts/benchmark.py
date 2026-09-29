#!/usr/bin/env python3
"""Heisenbug evaluation: true-positive rate and false-positive rate.

A flake classifier has to be judged on two axes, and most tools only report one:

  1. Does it find real flakes and name the right cause?  (true positives)
  2. Does it stay quiet on healthy suites?               (false positives)

Axis 2 matters as much as axis 1. A detector that always finds something is
useless, because you can never trust it when it does.

    python scripts/benchmark.py            # full run (clones real repos)
    python scripts/benchmark.py --quick    # demo target only

Results are written to benchmark_results.json.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import classify  # noqa: E402
from backend.hunt import Heisenbug  # noqa: E402

# Ground truth for the bundled suite: known entropy source per test.
DEMO_TRUTH = {
    "test_tag_ordering": classify.STARTUP_SEEDED,
    "test_concurrent_counter": classify.TRUE_RUNTIME,
    "test_cache_timestamp": classify.TRUE_RUNTIME,
    "test_addition": classify.DETERMINISTIC_PASS,
    "test_string": classify.DETERMINISTIC_PASS,
}

# Mature, well-maintained libraries. We assert nothing about their internals —
# only that a healthy suite should produce no flake findings.
CLEAN_TARGETS = ["boltons", "pyjwt", "diskcache", "tenacity"]


def run(target: str) -> dict:
    out: dict = {}
    t0 = time.time()

    def emit(ev, d):
        if ev == "done":
            out.update(d)

    Heisenbug("", emit, target_key=target).run()
    out["_secs"] = round(time.time() - t0, 1)
    return out


def main() -> int:
    quick = "--quick" in sys.argv
    report: dict = {"true_positive": {}, "false_positive": {}}

    # ---- axis 1: does it find real flakes, with the right cause? ----------
    print("=" * 66)
    print("AXIS 1 — true positives (bundled suite, ground truth known)")
    print("=" * 66)
    trials = 3
    correct = total = 0
    for i in range(trials):
        r = run("demo")
        got = {v["test"]: v["cls"] for v in r["verdicts"]}
        hits = sum(1 for t, want in DEMO_TRUTH.items() if got.get(t) == want)
        correct += hits
        total += len(DEMO_TRUTH)
        print(f"  trial {i+1}: {hits}/{len(DEMO_TRUTH)} correct  ({r['_secs']}s)")
    report["true_positive"] = {
        "trials": trials, "correct": correct, "total": total,
        "rate": round(correct / total, 4),
    }
    print(f"  -> {correct}/{total} = {correct/total:.0%} correct classification\n")

    if quick:
        json.dump(report, open("benchmark_results.json", "w"), indent=2)
        return 0

    # ---- axis 2: does it stay quiet on healthy suites? -------------------
    print("=" * 66)
    print("AXIS 2 — false positives (mature libraries, expect zero findings)")
    print("=" * 66)
    tests_seen = findings = 0
    for tgt in CLEAN_TARGETS:
        try:
            r = run(tgt)
        except Exception as exc:
            print(f"  {tgt:<12} SKIPPED ({type(exc).__name__}: {str(exc)[:60]})")
            continue
        n = len(r.get("verdicts", []))
        flaky = r.get("true_runtime", 0) + r.get("startup_seeded", 0)
        tests_seen += n
        findings += flaky
        status = "clean" if flaky == 0 else f"{flaky} FINDINGS"
        print(f"  {tgt:<12} {n:>4} tests  {r.get('runs',0):>3} suite runs  "
              f"{status:<12} ({r['_secs']}s)")
        report["false_positive"][tgt] = {"tests": n, "flaky_found": flaky,
                                         "secs": r["_secs"]}

    report["false_positive"]["_totals"] = {
        "tests": tests_seen, "false_positives": findings,
        "rate": round(findings / tests_seen, 5) if tests_seen else None,
    }
    print(f"\n  -> {findings} false positives across {tests_seen} real tests")

    json.dump(report, open("benchmark_results.json", "w"), indent=2)
    print("\nwrote benchmark_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
