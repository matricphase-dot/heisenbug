"""Flake classification by differential execution.

The classifier reads a test's divergence signature across fork points, ordered
earliest -> latest along the execution timeline, and assigns a cause class.

Signature semantics (D = diverges from identical state, S = stable):

    D D D   entropy is live at every fork point, including the latest
            -> TRUE RUNTIME nondeterminism (thread scheduling, wall clock, I/O)
            -> cannot be fixed by seeding; needs synchronisation or injection

    D S S   entropy was live before the snapshot but frozen after it
            -> STARTUP SEEDED (hash ordering, PID, env, RNG seeded at import)
            -> fixable by pinning the seed

    S S S   no divergence from identical state at any point
            -> DETERMINISTIC. Either a genuine always-failure or an always-pass.

    D D S   entropy enters between the two fork points where the flip occurs
            -> localised to that window; the bisector narrows it further

The transition index — the earliest fork point at which divergence STOPS — is
the bisection result: it names the window in which nondeterminism entered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TRUE_RUNTIME = "true_runtime"
STARTUP_SEEDED = "startup_seeded"
DETERMINISTIC_FAIL = "deterministic_fail"
DETERMINISTIC_PASS = "deterministic_pass"

LABEL = {
    TRUE_RUNTIME: "True runtime nondeterminism",
    STARTUP_SEEDED: "Startup-seeded nondeterminism",
    DETERMINISTIC_FAIL: "Deterministic failure (not flaky)",
    DETERMINISTIC_PASS: "Deterministic pass",
}

EXPLAIN = {
    TRUE_RUNTIME: (
        "Diverges even when every replica starts from byte-identical state at the "
        "latest fork point. The entropy source is live during execution — thread "
        "interleaving, wall-clock reads, or real I/O. Pinning a seed cannot fix this."
    ),
    STARTUP_SEEDED: (
        "Diverges when forked before interpreter startup, but is perfectly stable "
        "when forked after. The nondeterminism was fixed once at startup — hash "
        "ordering, PID, environment, or a module-level RNG seed. Pinning it is a "
        "complete fix."
    ),
    DETERMINISTIC_FAIL: (
        "Never diverges across any fork point. This is a real, reproducible bug "
        "being mis-triaged as flaky."
    ),
    DETERMINISTIC_PASS: "Stable and passing at every fork point.",
}

# Remediation strategy per class — consumed by the patch synthesiser.
REMEDY = {
    TRUE_RUNTIME: (
        "Introduce synchronisation or inject the nondeterministic dependency: a lock "
        "around the read-modify-write, or a clock/IO seam the test can control."
    ),
    STARTUP_SEEDED: (
        "Pin the startup entropy (PYTHONHASHSEED, explicit sort, or an explicit RNG "
        "seed) so ordering is defined rather than incidental."
    ),
    DETERMINISTIC_FAIL: "Fix the underlying bug; this is not a flake.",
    DETERMINISTIC_PASS: "No action required.",
}


@dataclass
class Verdict:
    test: str
    cls: str
    signature: list[bool]                 # diverges? per fork point, in order
    fail_rates: list[float] = field(default_factory=list)
    transition: str | None = None         # fork point where divergence stops
    window: tuple[str, str] | None = None # (last diverging, first stable)
    confidence: float = 0.0
    note: str = ""                        # statistical justification

    @property
    def label(self) -> str:
        return LABEL[self.cls]

    def to_json(self) -> dict:
        return {
            "test": self.test,
            "cls": self.cls,
            "label": self.label,
            "signature": self.signature,
            "fail_rates": [round(r, 3) for r in self.fail_rates],
            "transition": self.transition,
            "window": list(self.window) if self.window else None,
            "confidence": round(self.confidence, 2),
            "explain": EXPLAIN[self.cls],
            "remedy": REMEDY[self.cls],
            "note": self.note,
        }


def classify(test: str, fork_points: list[str], reports: list[dict]) -> Verdict:
    """reports[i] is the divergence entry for `test` at fork_points[i]."""
    sig = [bool(r.get("diverges")) for r in reports]
    rates = [float(r.get("fail_rate", 0.0)) for r in reports]

    if not any(sig):
        # Stable everywhere: distinguish always-fail from always-pass.
        always_fail = all(r.get("fail_rate", 0) >= 0.999 for r in reports)
        cls = DETERMINISTIC_FAIL if always_fail else DETERMINISTIC_PASS
        return Verdict(test, cls, sig, rates, confidence=_conf(reports))

    # --- Guard against sampling error -------------------------------------
    # A test that fails p of the time appears unanimous in n replicas with
    # probability p^n + (1-p)^n, which is NOT negligible for moderate p and
    # small n. So "stable at the last fork point" is only trustworthy if the
    # observation is also CONSISTENT with the earlier fork points.
    #
    # Decisive evidence for STARTUP_SEEDED is a monotone D...DS...S signature:
    # divergence must stop once and never resume. Anything non-monotone (DDS
    # after SDD, or DSD) means we are sampling a rare event, not observing a
    # real transition — in that case the entropy is still live and the correct
    # class is TRUE_RUNTIME.
    monotone = _is_monotone(sig)

    if sig[-1] or not monotone:
        # Diverging at the latest fork point, or an inconsistent signature that
        # unanimity could have produced by chance -> live entropy.
        return Verdict(test, TRUE_RUNTIME, sig, rates,
                       transition=None, confidence=_conf(reports))

    # Monotone D->S: candidate genuine transition. Find where it stops.
    idx = next(i for i in range(len(sig)) if not sig[i] and any(sig[:i]))

    # How surprised should we be that the later fork points looked unanimous?
    # Estimate the true fail rate from the DIVERGING observations, then ask how
    # often that rate would produce unanimity by chance across the stable runs.
    div_rates = [r for r, d in zip(rates, sig) if d]
    est_p = sum(div_rates) / len(div_rates) if div_rates else 0.0
    n_stable = min((reports[i].get("total", 0) for i in range(len(sig)) if not sig[i]),
                   default=0)

    # One-sided: the stable runs settled on a specific outcome, so we only ask
    # how likely THAT outcome was to occur unanimously by chance — not the
    # two-sided "either outcome" probability. A test diverging at 90% that then
    # settles at all-fail is evidence of a real transition, whereas the
    # two-sided figure would wrongly flag it as a likely fluke.
    stable_rates = [r for r, d in zip(rates, sig) if not d]
    settled_fail = bool(stable_rates) and stable_rates[0] >= 0.5
    if n_stable:
        q = est_p if settled_fail else (1 - est_p)
        # EVERY stable fork point is an independent trial that came out
        # unanimous. Accumulate across all of them, not just the smallest —
        # two independent unanimous runs are far stronger evidence than one.
        stable_totals = [reports[i].get("total", 0)
                         for i in range(len(sig)) if not sig[i]]
        p_fluke = 1.0
        for nt in stable_totals:
            p_fluke *= q ** nt
    else:
        p_fluke = 1.0

    # If unanimity was reasonably likely by chance, we have not proven a
    # transition — the honest classification is live entropy, under-sampled.
    if p_fluke > 0.05:
        v = Verdict(test, TRUE_RUNTIME, sig, rates, transition=None,
                    confidence=_conf(reports))
        v.note = (
            f"Signature suggested a transition, but a test failing ~{est_p:.0%} of "
            f"the time yields unanimous runs by chance with p={p_fluke:.2f} at "
            f"{n_stable} replicas. Not enough evidence for a seeded cause; "
            f"increase HB_REPLICAS to sharpen."
        )
        return v

    v = Verdict(
        test, STARTUP_SEEDED, sig, rates,
        transition=fork_points[idx],
        window=(fork_points[idx - 1], fork_points[idx]),
        confidence=_conf(reports),
    )
    v.note = (
        f"Transition is significant: chance of unanimity at {n_stable} replicas "
        f"given a ~{est_p:.0%} fail rate is only p={p_fluke:.3f}."
    )
    return v


def _is_monotone(sig: list[bool]) -> bool:
    """True iff the signature is D* S* — divergence stops once, never resumes."""
    seen_stable = False
    for d in sig:
        if not d:
            seen_stable = True
        elif seen_stable:
            return False      # diverged again after going stable
    return True


def unanimity_probability(fail_rate: float, n: int) -> float:
    """P(all n replicas agree) for a test that truly fails at `fail_rate`.

    Used to report how much the 'stable' observations can be trusted.
    """
    p = max(min(fail_rate, 1.0), 0.0)
    return p ** n + (1 - p) ** n


def _conf(reports: list[dict]) -> float:
    """Confidence grows with replica count and with decisive (non-marginal) splits."""
    if not reports:
        return 0.0
    n = min(r.get("total", 0) for r in reports)
    if n == 0:
        return 0.0
    # A 50/50 split is the strongest divergence evidence; 1/12 is weak.
    sharp = max(
        min(r.get("fail_rate", 0), 1 - r.get("fail_rate", 0)) * 2 for r in reports
    )
    base = min(n / 12.0, 1.0)
    return round(min(0.5 * base + 0.5 * sharp + 0.25, 0.99), 2)
