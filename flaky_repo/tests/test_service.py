"""A service test suite containing three DIFFERENT classes of nondeterminism.

On a CI retry dashboard all three look identical: "sometimes fails".
Heisenbug separates them by differential execution from identical state.
"""

import threading
import time

# ---------------------------------------------------------------------------
# Class A — STARTUP-SEEDED nondeterminism.
# Set iteration order depends on PYTHONHASHSEED, which is chosen once when the
# interpreter starts. Fork before startup -> replicas disagree.
# Fork after startup  -> every replica inherits the same seed -> they agree.
# ---------------------------------------------------------------------------
def test_tag_ordering():
    # Two elements only: which one iterates first is a ~50/50 coin flip
    # decided entirely by the startup hash seed.
    tags = {"alpha", "beta"}
    assert list(tags)[0] == "alpha"


# ---------------------------------------------------------------------------
# Class B — TRUE RUNTIME nondeterminism (thread scheduling).
# A read-modify-write on shared state with a narrow, clock-gated yield window.
# The interleaving is decided by the OS scheduler *during* the run, so replicas
# disagree even when launched from byte-identical state.
# ---------------------------------------------------------------------------
_counter = 0
_ITERS = 1000


def _bump():
    global _counter
    for _ in range(_ITERS):
        v = _counter
        if time.perf_counter_ns() % 150 == 0:
            time.sleep(0)          # rare, live-timing-gated scheduler yield
        _counter = v + 1


def test_concurrent_counter():
    global _counter
    _counter = 0
    ts = [threading.Thread(target=_bump) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert _counter == 2 * _ITERS


# ---------------------------------------------------------------------------
# Class B — TRUE RUNTIME nondeterminism (wall clock).
# The assertion is a predicate over live time, an uncontrolled external input.
# ---------------------------------------------------------------------------
def test_cache_timestamp():
    t = time.time()
    assert int(t * 1000) % 3 != 0


# ---------------------------------------------------------------------------
# Deterministic controls — must never diverge.
# ---------------------------------------------------------------------------
def test_addition():
    assert 1 + 1 == 2


def test_string():
    assert "ab".upper() == "AB"
