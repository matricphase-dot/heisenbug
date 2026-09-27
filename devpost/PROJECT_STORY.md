## Inspiration

Ask any engineer about flaky tests and you get the same story: a test fails in CI, you hit retry, it passes, you move on. The industry-standard tool is `pytest --count=100`, and it answers exactly one question — **how often does it fail?**

That number is nearly useless for fixing it, and the reason is structural: **every one of those 100 re-runs starts from a different state.** Fresh PID, fresh hash seed, fresh clock, fresh page cache. When you see "failed 12/100," you've measured a frequency and learned nothing about the mechanism.

Then we read the Nebius Token Factory **Sandboxes** docs and found something that changes the question. ConTree's branching model means `state.run(...)` doesn't mutate a state — it returns a **new state branched from it**. Call it N times on the same parent and you get N executions that each began from *byte-identical* state.

That makes a different experiment possible:

> Launch N replicas from **one shared checkpoint** and ask whether they *still* disagree.

This converts a frequency measurement into a **causal proof**.

## What it does

Heisenbug sweeps a fork point along the execution timeline and, at each point, launches N replicas from identical state.

- **Replicas diverge from identical state** → the entropy source is **live during execution** (thread scheduling, wall clock, real I/O). No seed will fix it.
- **Replicas agree from identical state**, but diverged when forked earlier → the entropy was **fixed once before that point** (hash seed, PID, module-level RNG). Pinning it is a complete fix.

Each test gets a signature across fork points. `D` = replicas from identical state disagreed, `S` = they all agreed.

| Signature | Class | Correct fix |
|---|---|---|
| `D D D` | True runtime nondeterminism | Lock, or inject a clock/IO seam |
| `D S S` | Startup-seeded nondeterminism | Pin the seed / sort explicitly |
| `S S S` all-fail | Deterministic failure — **not flaky at all** | Fix the actual bug |
| `S S S` all-pass | Deterministic pass | Nothing |

**This distinction is the entire product.** On a CI retry dashboard the first two classes are indistinguishable — both are just "sometimes fails." But **their fixes are mutually wrong.** Pinning a seed does nothing for a thread race; adding a lock does nothing for hash ordering. Heisenbug separates them mechanically, from execution evidence, before any model is asked for an opinion.

Then NVIDIA Nemotron explains each one, writes a deterministic repro recipe, and generates a **class-appropriate** patch.

## How we built it

**Execution — Nebius Token Factory Sandboxes (`contree-sdk`).** One checkpoint per fork point; `replicate(fork_point, n)` branches it n times so every replica starts byte-identical. A useful property falls out of ConTree's design: each state's `uuid` is derived from its content, so branches of a *deterministic* command collapse to the same uuid while a *nondeterministic* one yields different uuids. We record those as corroborating evidence alongside the test outcomes.

**Classification — mechanical, not model-driven.** Verdicts come from divergence signatures plus statistics. The LLM never votes on the diagnosis.

**NVIDIA Nemotron on Nebius Token Factory** (OpenAI-compatible endpoint), three tiers routed by job:

```
nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B    per-test evidence summarisation (highest volume)
nvidia/nemotron-3-super-120b-a12b        causal explanation, repro recipe, patch synthesis
nvidia/Nemotron-3-Ultra-550b-a55b        cross-suite causal report
```

The patch prompt carries the mechanical class and explicitly forbids the wrong remedy for that class.

**Backend** — FastAPI + Server-Sent Events. **Frontend** — zero-dependency HTML with a live divergence matrix.

## Verified result

Against a suite with three deliberately different entropy sources plus two deterministic controls, Heisenbug produces the correct classification on every run:

```
SSS  test_addition              Deterministic pass
DDD  test_cache_timestamp       True runtime nondeterminism     (wall clock)
DDD  test_concurrent_counter    True runtime nondeterminism     (thread scheduling)
SSS  test_string                Deterministic pass
DSS  test_tag_ordering          Startup-seeded nondeterminism   (PYTHONHASHSEED)
```

And given only the mechanical class, **Nemotron produced three different, correct fixes**:

| Test | Class | Nemotron's fix |
|---|---|---|
| `test_tag_ordering` | startup-seeded | `sorted(tags)` — defined ordering |
| `test_concurrent_counter` | true runtime | `threading.Lock` around the read-modify-write |
| `test_cache_timestamp` | true runtime | `patch('time.time')` — inject a controllable clock |

It never pinned a seed for the thread race, and never added a lock for hash ordering. Nemotron Ultra's report independently raised hash randomisation **and ASLR** as candidate startup entropy sources — neither appeared in the prompt.

## Statistical honesty (the hard part)

A test failing at rate *p* appears unanimous across *n* replicas with probability `p^n + (1-p)^n` — **not** negligible for moderate *p* and small *n*. A naive classifier reads that accidental unanimity as a real transition and confidently reports the wrong cause.

We hit this for real: a thread race firing at ~6% under parallel load produced unanimous batches often enough to be misclassified as startup-seeded. Three guards fix it:

1. **Monotonicity.** Only a `D…D S…S` signature counts as a transition. Divergence that stops and resumes means we're sampling a rare event, not observing a boundary.
2. **One-sided significance.** Estimate the true fail rate from the diverging fork points, then compute how likely the observed unanimity was by chance — accumulated across *every* stable fork point as independent trials.
3. **Adaptive re-sampling.** When evidence is marginal (`p > 0.05`), Heisenbug doesn't guess. It **forks more replicas and re-measures.**

Every verdict ships with the statistical note that justifies it.

## A negative result we're publishing on purpose

We ran the full sweep against **`grantjenks/python-diskcache`** at commit `ebfa37c`: 92 real tests, 3 fork points, 12 replicas each — **36 complete suite runs**. Result: **zero flaky tests.** Every test classified `SSS`.

We report that plainly because **a flake detector that cannot return "clean" is useless.** A tool that always finds something is a tool you cannot trust when it does.

We also probed specifically and could not manufacture flakiness in mature libraries on 2 vCPUs: diskcache's `throttle()` doctest asserts `count in (6, 7)` with upstream's own comment *"depending on CPU load"* — it held across 12 concurrent replicas and 6 CPU burners. tenacity's timing-heavy suite: 141 tests, zero divergence.

## Challenges we ran into

- **Building an honestly intermittent race was genuinely hard.** CPython 3.13 optimises the obvious `v = c; c = v + 1` so it never loses updates, while a forced `time.sleep(0)` every iteration loses them *always*. We binary-searched the yield probability to land a race that fires ~40% of the time under real replica load.
- **The first classifier was confidently wrong.** It read one unanimous batch as proof of a transition. Fixing that properly — rather than tuning a threshold until the demo looked good — produced the significance machinery above.
- **Nemotron's reasoning tiers truncate structured output.** They spend a large, variable share of `max_tokens` on `reasoning_content` before the answer, so a conservative budget silently cuts the JSON mid-string while still reporting `finish_reason: "stop"`. Our first live run lost 2 of 3 analysis calls. Fixed with a salvage parser that closes unterminated strings/braces, plus one retry at double budget.
- **A shipped build of the hosted demo was broken.** Our build script stripped two helper functions; the page returned HTTP 200 and looked fine to `curl`, but every replay event threw `ReferenceError`. We now have a headless-DOM regression test that actually executes the page instead of checking status codes.

## Sandboxes access — full transparency

Diagnosing Sandboxes turned up a real SDK trap: **`ContreeSync(token=...)` silently selects `JWTAuth`**, which omits the `Project` header Sandboxes requires. The API answers `400 Missing "Project" header`, but through the SDK it surfaces as a bare `ForbiddenError` pointing nowhere near the cause. Sandboxes needs `IAMAuth(token=..., project_id=...)`.

With that corrected and a verified project ID, the API returns `403 Insufficient permissions` — a missing Sandboxes role on the service account, which only Nebius can grant while Sandboxes is in Beta. `prepare()` catches this and falls back to the local executor automatically, so the investigation never aborts.

**We are stating this plainly rather than implying Sandbox execution we did not have.** The method, the classifier and the statistics are executor-independent; the moment the role is granted, the same code path runs against real Sandbox branches with no changes. `python scripts/verify_setup.py` reports exactly which condition you hit.

## Accomplishments we're proud of

- **A genuinely new diagnostic primitive.** Prior flaky-test work either re-runs (no causal signal) or does heavyweight deterministic record-and-replay (rr, Hermit) requiring special tooling and large slowdowns. Heisenbug gets causal evidence from cheap state branching, with **zero instrumentation** of the program under test.
- **The classifier is mechanical.** No LLM-as-judge in the decision path.
- **It knows when it doesn't know**, and responds by gathering more evidence rather than asserting.
- **It reports clean suites as clean** — and we published that negative result.
- **Runs with no credentials** — identical method, local executor, ~20 seconds, so judges can evaluate without keys.

## What we learned

Cheap state branching isn't a convenience feature — it **changes which experiments are possible**. Deterministic replay has existed for years but is too heavy for routine CI use. Sandbox branching gets a large fraction of the causal signal at a fraction of the cost.

We also learned to be disciplined about where the LLM sits. Our first instinct was to let the model classify the flake. Making classification mechanical and reserving the model for *explanation* made the system both more accurate and far easier to trust.

## What's next for Heisenbug

- **CI integration**: run on changed tests per-PR, comment the signature, class and patch.
- **Finer fork-point granularity** — per-fixture and per-test-phase checkpoints to narrow the entropy window from a phase to a line.
- **Flake regression gating**: fail a PR that introduces a `DDD` test.
- **Real-world validation** against known-flaky tests in large open-source projects, on hardware that can actually reproduce CI scheduling pressure.
