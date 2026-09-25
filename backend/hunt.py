"""Heisenbug orchestrator: differential execution -> classification -> fixes.

Pipeline
--------
1. SWEEP   For each fork point (earliest -> latest), launch N replicas from
           byte-identical state and record per-test pass/fail.
2. CLASSIFY Read each test's divergence signature across fork points and assign
           a cause class. The fork point where divergence STOPS localises the
           entropy source in time — this is the bisection.
3. EXPLAIN Nemotron turns the divergence evidence into a causal explanation,
           a deterministic repro recipe, and a class-appropriate patch.
4. REPORT  Nemotron Ultra writes the cross-suite causal summary.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from . import classify, config, nebius, targets
from .executor import divergence, make_executor

ANALYST_SYSTEM = """You are a concurrency and nondeterminism specialist analysing a flaky test.
You are given: the test source, its divergence signature measured across fork points
(whether replicas launched from BYTE-IDENTICAL execution state disagreed), and a
mechanically-derived cause class.

Explain the specific entropy source, give a deterministic repro recipe, and write a
patch appropriate to the cause class. Never pin a seed for true runtime nondeterminism;
never add a lock for startup-seeded ordering.

Respond with JSON only: {"summary": str, "repro": str, "patch": str}"""

REPORT_SYSTEM = """You are writing the final causal report for a flaky test investigation.
You are given every test's divergence signature and cause class. Explain what the
differential-execution evidence proves, why these classes require different fixes, and
why a retry-count dashboard could not have distinguished them. Be concise and concrete.
Plain prose, no JSON."""


class Heisenbug:
    def __init__(self, repo_dir: str, emit: Callable[[str, dict], None],
                 target_key: str = "demo"):
        self.target = targets.get(target_key)
        self.repo_dir = self.target.local_path or repo_dir
        self.emit = emit
        self.ex = make_executor(self.repo_dir, self.target)
        srcs = self.target.source_files or ["tests/test_service.py"]
        self.test_file = srcs[0]

    def log(self, msg: str, kind: str = "info") -> None:
        self.emit("log", {"msg": msg, "kind": kind})

    def run(self) -> dict:
        self.log(f"Target: {self.target.name}", "meta")
        if self.target.notes:
            self.log(self.target.notes, "meta")
        self.log(f"Executor: {self.ex.name} · {config.REPLICAS} replicas per fork point", "meta")
        self.log("Materialising target (clone + install if needed)…", "info")
        try:
            self.ex.prepare()
        except Exception as exc:
            # Sandboxes is Beta and gated per-account; a permission error here
            # must not abort the investigation. The local executor implements
            # the identical experiment.
            from .executor import LocalForkExecutor

            self.log(f"Sandboxes unavailable ({type(exc).__name__}: "
                     f"{str(exc)[:90]}) — falling back to local executor.", "warn")
            self.ex = LocalForkExecutor(self.repo_dir, self.target)
            self.ex.prepare()
            self.log(f"Executor: {self.ex.name}", "meta")

        # ---- 1. Sweep fork points -----------------------------------------
        matrix: dict[str, dict] = {}
        for fp in config.FORK_POINTS:
            self.log(f"── Fork point '{fp}': launching {config.REPLICAS} "
                     f"replicas from identical state ──", "phase")
            outcomes = self.ex.replicate(fp, config.REPLICAS)
            rep = divergence(outcomes)
            matrix[fp] = rep

            div = [t for t, r in rep.items() if r["diverges"]]
            for t in sorted(rep):
                r = rep[t]
                self.emit("cell", {
                    "fork_point": fp, "test": t,
                    "failed": r["failed"], "total": r["total"],
                    "diverges": r["diverges"], "fail_rate": r["fail_rate"],
                })
            self.log(
                f"{len(div)} test(s) diverged from identical state: "
                + (", ".join(div) if div else "none"),
                "bad" if div else "good",
            )

        # ---- 2. Classify (with adaptive re-sampling) ------------------------
        self.log("── Classifying by divergence signature ──", "phase")
        tests = sorted({t for rep in matrix.values() for t in rep})
        verdicts: list[classify.Verdict] = []
        for t in tests:
            reports = [matrix[fp].get(t, {}) for fp in config.FORK_POINTS]
            v = classify.classify(t, config.FORK_POINTS, reports)

            # A monotone D->S signature that failed the significance gate is not
            # a wrong answer — it is an under-sampled one. Forking is cheap, so
            # buy more evidence instead of guessing.
            if v.cls == classify.TRUE_RUNTIME and classify._is_monotone(v.signature) \
                    and any(v.signature) and not v.signature[-1]:
                self.log(f"{t}: marginal evidence, re-sampling stable fork points "
                         f"at {config.REPLICAS * 2} replicas…", "warn")
                for i, fp in enumerate(config.FORK_POINTS):
                    if not v.signature[i]:
                        extra = divergence(self.ex.replicate(fp, config.REPLICAS * 2))
                        got = extra.get(t, {})
                        base = matrix[fp].get(t, {})
                        merged = {
                            "failed": base.get("failed", 0) + got.get("failed", 0),
                            "passed": base.get("passed", 0) + got.get("passed", 0),
                        }
                        merged["total"] = merged["failed"] + merged["passed"]
                        merged["diverges"] = 0 < merged["failed"] < merged["total"]
                        merged["fail_rate"] = (merged["failed"] / merged["total"]
                                               if merged["total"] else 0.0)
                        matrix[fp][t] = merged
                        self.emit("cell", {"fork_point": fp, "test": t, **merged})
                reports = [matrix[fp].get(t, {}) for fp in config.FORK_POINTS]
                v = classify.classify(t, config.FORK_POINTS, reports)

            verdicts.append(v)
            sig = "".join("D" if d else "S" for d in v.signature)
            self.emit("verdict", v.to_json())
            kind = {
                classify.TRUE_RUNTIME: "bad",
                classify.STARTUP_SEEDED: "warn",
                classify.DETERMINISTIC_FAIL: "warn",
                classify.DETERMINISTIC_PASS: "good",
            }[v.cls]
            extra = ""
            if v.window:
                extra = f" · entropy enters between '{v.window[0]}' and '{v.window[1]}'"
            self.log(f"[{sig}] {t} → {v.label}{extra}", kind)

        # ---- 3. Explain + patch (Nemotron, parallel) ------------------------
        flaky = [v for v in verdicts
                 if v.cls in (classify.TRUE_RUNTIME, classify.STARTUP_SEEDED)]
        if flaky:
            self.log(f"── Synthesising repro + fix for {len(flaky)} flaky test(s) · "
                     f"{config.MODEL_SUPER} ──", "phase")
            src = "\n\n".join(
                f"--- {f} ---\n{self.ex.source(f)}"
                for f in (self.target.source_files or [self.test_file])
            )
            with ThreadPoolExecutor(max_workers=max(len(flaky), 1)) as pool:
                list(pool.map(lambda v: self._analyse(v, src), flaky))

        # ---- 4. Final causal report (Ultra) ---------------------------------
        self.log(f"── Causal report · {config.MODEL_ULTRA} ──", "phase")
        report = ""
        try:
            summary_input = "\n".join(
                f"{v.test}: signature={''.join('D' if d else 'S' for d in v.signature)} "
                f"class={v.cls} fail_rates={[round(r,2) for r in v.fail_rates]}"
                for v in verdicts
            )
            report = nebius.chat(
                config.MODEL_ULTRA, REPORT_SYSTEM,
                f"FORK POINTS (earliest to latest): {config.FORK_POINTS}\n\n{summary_input}",
                temperature=0.2,
            ).strip()
            self.emit("report", {"text": report})
        except Exception as exc:
            self.log(f"Report unavailable: {exc}", "warn")

        payload = {
            "target": {"key": self.target.key, "name": self.target.name,
                       "description": self.target.description,
                       "notes": self.target.notes},
            "verdicts": [v.to_json() for v in verdicts],
            "report": report,
            "fork_points": config.FORK_POINTS,
            "replicas": config.REPLICAS,
            "runs": len(config.FORK_POINTS) * config.REPLICAS,
            "true_runtime": sum(1 for v in verdicts if v.cls == classify.TRUE_RUNTIME),
            "startup_seeded": sum(1 for v in verdicts if v.cls == classify.STARTUP_SEEDED),
        }
        self.emit("done", payload)
        return payload

    def _analyse(self, v: classify.Verdict, src: str) -> None:
        sig = "".join("D" if d else "S" for d in v.signature)
        prompt = (
            f"TEST: {v.test}\n"
            f"DIVERGENCE SIGNATURE across {config.FORK_POINTS}: {sig}\n"
            f"(D = replicas from byte-identical state disagreed, S = all agreed)\n"
            f"FAIL RATES: {[round(r, 2) for r in v.fail_rates]}\n"
            f"MECHANICAL CLASS: {v.cls} — {classify.EXPLAIN[v.cls]}\n"
            f"REQUIRED REMEDY DIRECTION: {classify.REMEDY[v.cls]}\n\n"
            f"TEST FILE SOURCE:\n{src}"
        )
        try:
            data = nebius.chat_json(
                config.MODEL_SUPER, ANALYST_SYSTEM, prompt, temperature=0.2
            )
            self.emit("analysis", {
                "test": v.test, "cls": v.cls,
                "summary": data.get("summary", ""),
                "repro": data.get("repro", ""),
                "patch": data.get("patch", ""),
            })
            self.log(f"{v.test}: {data.get('summary','')[:110]}…", "model")
        except Exception as exc:
            self.log(f"{v.test}: analysis failed ({exc})", "warn")
