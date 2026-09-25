# Heisenbug — Differential Execution Flake Hunter

**Nebius x NVIDIA Global AI Hackathon — Coding & Agentic Engineering Track**

> Re-running a test suite 100 times tells you a test is flaky. It never tells you **why** —
> because every re-run starts from a *different* state. Heisenbug launches replicas from
> **byte-identical execution state**, which turns flakiness from a statistic into a
> **controlled experiment**.

---

## The core idea

Classical flaky-test hunting is `pytest --count=100`. Every one of those runs has a fresh PID,
a fresh hash seed, a fresh clock, a fresh page cache. So when you observe *"failed 12/100"*, you
have measured **that** a test is flaky and learned nothing about **why**.

Nebius Token Factory **Sandboxes** can fork live execution state. That makes a new experiment
possible, one that was previously impractical:

> Launch N replicas from **one shared checkpoint** — byte-identical state — and see whether
> they still disagree.

This single change converts a frequency measurement into a **causal proof**:

- **Replicas diverge from identical state** → the entropy source is **live during execution**
  (thread scheduling, wall clock, real I/O). No seed can fix it.
- **Replicas agree from identical state**, but diverged when forked earlier → the entropy was
  **fixed once, before the fork** (hash seed, PID, env, module-level RNG). Pinning it is a
  complete fix.

Sweep the fork point from early to late along the execution timeline and watch **where divergence
stops**. That is a bisection over *when* nondeterminism enters.

## Divergence signatures

Each test gets a signature across fork points, earliest → latest. `D` = replicas from identical
state disagreed, `S` = they all agreed.

| Signature | Class | Meaning | Correct fix |
|---|---|---|---|
| `D D D` | **True runtime** | Still diverges at the latest fork point — entropy is live | Lock / inject the clock / add a seam |
| `D S S` | **Startup-seeded** | Diverged before startup, stable after — entropy was burned in at interpreter start | Pin the seed or sort explicitly |
| `S S S` (all fail) | **Deterministic failure** | Never diverges — a real bug mis-triaged as flaky | Fix the bug |
| `S S S` (all pass) | **Deterministic pass** | Stable and green | Nothing |

**This is the whole point:** on a CI retry dashboard, the first two classes look *identical* —
both are just "sometimes fails". But **their fixes are mutually wrong.** Pinning a seed does
nothing for a thread race. Adding a lock does nothing for hash ordering. Heisenbug separates them
mechanically, from execution evidence, before a model is ever asked for an opinion.

## Verified result

Against `flaky_repo` — a suite with three deliberately different entropy sources plus two
deterministic controls — Heisenbug produces the correct classification **10 out of 10 runs**:

```
SSS  test_addition              Deterministic pass
DDD  test_cache_timestamp       True runtime nondeterminism     (wall clock)
DDD  test_concurrent_counter    True runtime nondeterminism     (thread scheduling)
SSS  test_string                Deterministic pass
DSS  test_tag_ordering          Startup-seeded nondeterminism   (PYTHONHASHSEED)
```

## Running against real repositories

Heisenbug is repo-agnostic. A target says how to clone, install, and invoke a suite; the
divergence sweep, classifier, and statistics never look at which project they are running.

```python
# backend/targets.py
DISKCACHE = Target(
    git_url="https://github.com/grantjenks/python-diskcache.git",
    install=["pip", "install", "-q", "-e", "."],
    pytest_args=["tests/test_recipes.py", "tests/test_core.py", "-o", "addopts="],
)
```

Pick the target from the dropdown; Heisenbug clones it, installs it, and sweeps it live.

### What we found on real code — including a negative result

We ran the full sweep against **`grantjenks/python-diskcache`** at `ebfa37c`: 92 real tests,
3 fork points, 12 replicas each — **36 full suite runs**. Result:

> **Zero flaky tests. Every test classified `SSS` — stable from identical state at every fork point.**

We report that plainly because it is the honest outcome, and because **a flake detector that
cannot return "clean" is useless.** A tool that always finds something is a tool you cannot trust
when it does.

We also probed specifically for flakiness in mature libraries and could not manufacture it here:

- `diskcache`'s `throttle()` doctest asserts `count in (6, 7)` with the upstream comment
  *"6 or 7 calls depending on CPU load"* — an explicitly load-dependent contract. It held across
  12 concurrent replicas, and still held with 6 CPU burners saturating both cores.
- `tenacity`'s timing-heavy suites: 141 tests, no divergence.
- `diskcache`'s millisecond-expiry tests (`expire=0.001` with a 10 ms sleep) survived 24 replicas
  plus 24 burner threads on 2 cores.

**The honest interpretation:** these are well-engineered libraries whose fast unit tests are
deliberately deterministic, and this 2-vCPU sandbox cannot reproduce the scheduling pressure of a
loaded CI fleet. The bundled demo target exists precisely because it has **known ground truth** —
it is how we verify the classifier is correct, rather than assuming it.

## Verified live on NVIDIA Nemotron

Confirmed against real models on Nebius Token Factory (not stubs):

```
nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B    per-test evidence summarisation
nvidia/nemotron-3-super-120b-a12b        explanation + repro + patch synthesis
nvidia/Nemotron-3-Ultra-550b-a55b        cross-suite causal report
```

**The core claim holds.** Given the mechanical class, Nemotron Super produced a
*different, correct* remedy for each cause — and never the wrong one for the class:

| Test | Class | Nemotron's fix |
|---|---|---|
| `test_tag_ordering` | startup-seeded | `sorted(tags)` — defined ordering, not incidental hash order |
| `test_concurrent_counter` | true runtime | `threading.Lock` around the read-modify-write |
| `test_cache_timestamp` | true runtime | `patch('time.time')` — inject a controllable clock |

No seed pinning for the thread race. No lock for hash ordering. Nemotron Ultra's report
independently reasoned about hash randomisation and ASLR as candidate startup entropy sources —
neither was mentioned in the prompt.

**Note on reasoning models:** Nemotron tiers emit `reasoning_content` before the answer, so a
tight `max_tokens` truncates the JSON payload. `chat_json()` handles this with a salvage parser
(closes unterminated strings/braces) plus one retry at double the budget. Failure rate went from
2-of-3 calls to 0-of-3 across repeated runs.

## Statistical honesty

A test failing at rate *p* looks unanimous across *n* replicas with probability `p^n + (1-p)^n`,
which is **not** negligible for moderate *p* and small *n*. A naive classifier reads that accidental
unanimity as a real transition and confidently reports the wrong cause.

Heisenbug guards against this explicitly:

1. **Monotonicity.** Only a `D…D S…S` signature counts as a transition. Divergence that stops and
   then resumes (`S D D`) means we are sampling a rare event, not observing a real boundary.
2. **One-sided significance.** Estimate the true fail rate from the diverging fork points, then
   compute how likely the observed unanimity was *by chance*, accumulated across **every** stable
   fork point as independent trials.
3. **Adaptive re-sampling.** If the evidence is marginal (`p > 0.05`), Heisenbug doesn't guess — it
   **forks more replicas and re-measures.** Forking is cheap, so buying evidence is the right move.

Every verdict carries the statistical note that justifies it.

## How NVIDIA Nemotron is used

The classification is **mechanical** — derived from execution evidence, not model opinion. Nemotron
is used for what models are actually good at: explanation and synthesis.

- **Nano** — per-test evidence summarisation (highest call volume).
- **Super** — causal explanation, deterministic repro recipe, and a **class-appropriate patch**.
  The prompt carries the mechanical class and forbids the wrong remedy: never pin a seed for a
  thread race, never add a lock for hash ordering.
- **Ultra** — the final cross-suite causal report explaining what the divergence matrix proves.

All served on **Nebius Token Factory** via its OpenAI-compatible endpoint.

## Run it

```bash
pip install -r requirements.txt
export NEBIUS_API_KEY=...        # https://tokenfactory.nebius.com/
export NEBIUS_PROJECT_ID=...
python -m uvicorn backend.server:app --host 0.0.0.0 --port 8000
# open http://localhost:8000
```

**Verify your setup first.** The moment your Token Factory credits land:

```bash
export NEBIUS_API_KEY=...
python scripts/verify_setup.py
```

It authenticates, lists the NVIDIA/Nemotron models actually available on your account, checks the
IDs in `backend/config.py` resolve, and runs a live inference smoke test. If an ID is wrong it
prints the exact `export` line to fix it. (Model IDs are all env-overridable, so no code changes.)

**No key?** Heisenbug runs the *identical* method against a local executor, where fork points are
emulated via `PYTHONHASHSEED` control while thread scheduling and the wall clock stay genuinely
live. Judges see the whole investigation in ~20 seconds with no credentials.

Tunables: `HB_REPLICAS` (default 12), `HB_MODEL_NANO` / `HB_MODEL_SUPER` / `HB_MODEL_ULTRA`.

## Validation

The classifier's decision logic is covered by its own test suite — synthetic divergence reports,
fast and deterministic:

```bash
python -m pytest tests/ -q     # 10 passed
```

It pins the behaviour that matters: non-monotone signatures are rejected, marginal unanimity is
not mistaken for a transition, and more replicas convert marginal evidence into decisive evidence.

## Layout

```
backend/
  config.py     model routing, fork points, replica budget
  targets.py    repo definitions (bundled demo + real git targets)
  executor.py   Sandboxes replication (fork -> N identical replicas) + local fallback
  classify.py   divergence signatures, monotonicity + significance guards
  hunt.py       orchestrator: sweep -> classify -> adaptive re-sample -> explain
  nebius.py     Token Factory client + offline stub
  server.py     FastAPI + SSE
frontend/
  index.html    live divergence matrix
flaky_repo/     three distinct entropy sources + two deterministic controls
tests/          validation suite for the classifier
```

## Why this needs Nebius specifically

Prior work on flaky tests either re-runs (no causal signal) or does heavyweight deterministic
record-and-replay (rr, Hermit) — which needs special tooling, imposes large slowdowns, and is hard
to run per-PR in CI. Heisenbug gets a causal signal from **cheap state forking alone**, using the
ordinary test suite, with no instrumentation of the program under test.

Research agents branch over *patches* or *messages* using logical replay. Heisenbug branches over
**identical live process state** — which is precisely the primitive Sandboxes provide and
conventional CI does not.

## License

Apache 2.0 — see `LICENSE`.
