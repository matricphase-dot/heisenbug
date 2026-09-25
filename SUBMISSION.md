# Heisenbug — Devpost Submission Copy

Paste-ready. Each section maps to a Devpost field.

---

## Project name
**Heisenbug**

## Tagline
> Re-running a test 100 times tells you it's flaky. Heisenbug launches replicas from byte-identical execution state — turning flakiness from a statistic into a controlled experiment that proves the cause.

## Track
**Coding and Agentic Engineering**

## Elevator pitch
Every flaky-test tool measures *how often* a test fails. None can tell you *why*, because every re-run starts from a different state. Heisenbug forks one checkpoint into N byte-identical replicas — so divergence becomes proof of live nondeterminism, and the fork point where divergence stops localises the entropy source in time.

---

## Inspiration

Ask any engineer about flaky tests and you get the same story: a test fails in CI, you hit retry, it passes, you move on. The industry-standard tool is `pytest --count=100`, and it answers exactly one question — *how often does this fail?*

That number is nearly useless for fixing it. Here's why: **every one of those 100 re-runs starts from a different state.** Fresh PID, fresh hash seed, fresh clock, fresh page cache. When you see "failed 12/100," you have measured a frequency and learned nothing about the mechanism.

We realised Nebius Token Factory Sandboxes make a fundamentally different experiment possible. If you can fork live execution state cheaply, you can launch N replicas from **one shared checkpoint** — byte-identical state — and ask whether they *still* disagree.

That single change converts a frequency measurement into a causal proof.

## What it does

Heisenbug sweeps a fork point along the execution timeline and, at each point, launches N replicas from identical state.

- **Replicas diverge from identical state** → the entropy source is **live during execution** (thread scheduling, wall clock, real I/O). No seed will ever fix it.
- **Replicas agree from identical state**, but diverged when forked earlier → the entropy was **fixed once before that point** (hash seed, PID, env, module-level RNG). Pinning it is a complete fix.

Each test gets a signature across fork points (`D` = diverged, `S` = stable):

| Signature | Class | Correct fix |
|---|---|---|
| `D D D` | True runtime nondeterminism | Lock, or inject a clock/IO seam |
| `D S S` | Startup-seeded nondeterminism | Pin the seed / sort explicitly |
| `S S S` all-fail | Deterministic failure — not flaky at all | Fix the actual bug |
| `S S S` all-pass | Deterministic pass | Nothing |

**This is the entire point.** On a CI retry dashboard the first two classes are indistinguishable — both are just "sometimes fails." But their fixes are *mutually wrong*. Pinning a seed does nothing for a thread race; adding a lock does nothing for hash ordering. Heisenbug separates them mechanically, from execution evidence, before any model is asked for an opinion.

Then Nemotron explains each one, writes a deterministic repro recipe, and generates a **class-appropriate** patch.

## How we built it

- **Execution — Nebius Token Factory Sandboxes (`contree-sdk`).** One checkpoint per fork point; `replicate(fork_point, n)` forks it n times so every replica starts byte-identical. This is the primitive the entire method rests on.
- **Classification — mechanical, not model-driven.** Verdicts come from divergence signatures. The LLM never votes on the diagnosis.
- **NVIDIA Nemotron on Nebius Token Factory** (OpenAI-compatible endpoint):
  - **Nano** — per-test evidence summarisation, the highest-volume call.
  - **Super** — causal explanation, repro recipe, and patch. The prompt carries the mechanical class and explicitly forbids the wrong remedy for that class.
  - **Ultra** — final cross-suite causal report over the whole divergence matrix.
- **Backend** — FastAPI + SSE. **Frontend** — zero-dependency HTML, live divergence matrix.

## Proving it on real repositories (including a negative result)

Heisenbug is repo-agnostic — a target defines how to clone, install and invoke a suite; the sweep, classifier and statistics never look at which project they are running. Pick a target from the dropdown and it clones and sweeps it live.

We ran the full sweep against **`grantjenks/python-diskcache`** at commit `ebfa37c`: 92 real tests, 3 fork points, 12 replicas each — **36 complete suite runs**. The result:

> **Zero flaky tests.** Every test classified `SSS` — stable from byte-identical state at every fork point.

We are reporting that plainly, because **a flake detector that cannot return "clean" is useless.** A tool that always finds something is a tool you cannot trust when it does.

We also went hunting specifically, and could not manufacture flakiness in mature libraries on this hardware:

- `diskcache`'s `throttle()` doctest asserts `count in (6, 7)` with upstream's own comment *"6 or 7 calls depending on CPU load"* — an explicitly load-dependent contract. It held across 12 concurrent replicas, and still held with 6 CPU burners saturating both cores.
- `tenacity`'s timing-heavy suites: 141 tests, zero divergence.
- `diskcache`'s millisecond-expiry tests (`expire=0.001`, 10 ms sleep) survived 24 replicas plus 24 burner threads on 2 cores.

The honest interpretation: these are well-engineered libraries whose fast unit tests are deliberately deterministic, and a 2-vCPU sandbox cannot reproduce the scheduling pressure of a loaded CI fleet. That is exactly why the bundled demo target exists — it has **known ground truth**, so it verifies the classifier is correct rather than assuming it.

## Verified live on NVIDIA Nemotron

Running against real models on Nebius Token Factory — `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/nemotron-3-super-120b-a12b`, and `nvidia/Nemotron-3-Ultra-550b-a55b`.

The central claim held up. Given the mechanical class, Nemotron Super produced a *different, correct* remedy for each cause:

| Test | Class | Nemotron's fix |
|---|---|---|
| `test_tag_ordering` | startup-seeded | `sorted(tags)` — defined ordering |
| `test_concurrent_counter` | true runtime | `threading.Lock` around the read-modify-write |
| `test_cache_timestamp` | true runtime | `patch('time.time')` — inject a controllable clock |

It never pinned a seed for the thread race, and never added a lock for hash ordering. Nemotron Ultra's causal report independently raised hash randomisation *and ASLR* as candidate startup entropy sources — neither appeared in the prompt.

**A real integration lesson:** Nemotron's reasoning tiers emit `reasoning_content` before the answer, so a conservative `max_tokens` silently truncates the JSON payload mid-string. Our first live run lost 2 of 3 analysis calls to parse errors. We fixed it with a salvage parser that closes unterminated strings and braces, plus one retry at double the budget with a brevity instruction. Failure rate went to zero across repeated runs. This is the kind of thing you only discover by running against the real models.

## On Sandboxes access — full transparency

Heisenbug ships two executors behind one interface. `NebiusForkExecutor` is written against ConTree's real branching API — where `state.run(...)` returns a *new* state branched from the parent instead of mutating it, so calling it N times on one parent gives N executions that each began from byte-identical state. `LocalForkExecutor` implements the identical experiment locally.

**Sandboxes is Beta and gated per-account.** Our account returns `ForbiddenError`, so the published runs used the local executor; `prepare()` catches this and falls back automatically. We are stating this plainly rather than implying Sandbox execution we did not have. The method, the classifier and the statistics are executor-independent — and the moment Beta access is granted, the same code path runs against real Sandbox branches with no changes.

One design detail worth flagging: ConTree derives each state's `uuid` from its content, so branches of a *deterministic* command collapse to the same uuid while a *nondeterministic* one produces different uuids. That is divergence detection handed to you by the platform, and `NebiusForkExecutor` records those uuids as corroborating evidence alongside the test outcomes.

## Statistical honesty (the hard part)

This is where most of the engineering went, and it's the part we're proudest of.

A test failing at rate *p* appears unanimous across *n* replicas with probability `p^n + (1-p)^n` — **not** negligible for moderate *p* and small *n*. A naive classifier reads that accidental unanimity as a real transition and confidently reports the wrong cause. We hit this for real during development: a thread race firing at ~6% under parallel load produced unanimous batches often enough to be misclassified as startup-seeded.

Three guards fix it:

1. **Monotonicity.** Only a `D…D S…S` signature counts as a transition. Divergence that stops and resumes (`S D D`) means we're sampling a rare event, not observing a boundary.
2. **One-sided significance.** Estimate the true fail rate from the diverging fork points, then compute how likely the observed unanimity was by chance — accumulated across *every* stable fork point as independent trials, and one-sided because the stable runs settled on a specific outcome.
3. **Adaptive re-sampling.** When evidence is marginal (`p > 0.05`), Heisenbug doesn't guess. It **forks more replicas and re-measures.** Forking is cheap; buying evidence is the correct move.

Every verdict ships with the statistical note that justifies it.

## Challenges we ran into

- **Building an honestly intermittent race was genuinely hard.** CPython 3.13 optimises the obvious `v = c; c = v + 1` pattern so it never loses updates, while a forced `time.sleep(0)` every iteration loses them *always*. Both extremes are useless for a demo. We binary-searched the yield probability to land a race that fires ~40% of the time under real replica load.
- **The first classifier was confidently wrong.** It read one unanimous batch as proof of a transition. Fixing this properly — rather than tuning a threshold until the demo looked good — is what produced the significance machinery above.
- **Fail rates shift under parallel load.** A race measured at 40% serially fired at 6% when 12 replicas ran concurrently. Measuring under realistic load, not in isolation, was essential.
- **Real mature libraries are hard to catch flaking on a small box.** We probed diskcache and tenacity extensively — including upstream's own explicitly load-dependent `throttle()` contract — and got clean results on 2 vCPUs. We shipped the negative result instead of engineering a failure.

## Accomplishments we're proud of

- **A genuinely new diagnostic primitive.** Prior flaky-test work either re-runs (no causal signal) or does heavyweight deterministic record-and-replay (rr, Hermit) requiring special tooling and large slowdowns. Heisenbug gets causal evidence from cheap state forking alone, with **zero instrumentation** of the program under test.
- **The classifier is mechanical.** No LLM-as-judge in the decision path — verdicts are execution evidence plus statistics. The model explains; it does not diagnose.
- **10/10 correct classifications** across repeated runs on a suite with three distinct entropy sources and two deterministic controls.
- **It knows when it doesn't know**, and responds by gathering more evidence rather than asserting.
- **Runs with no credentials** — identical method, local executor, ~20 seconds.
- **It reports clean suites as clean.** We swept a real 92-test library and returned zero findings, and we published that rather than tuning until something lit up.
- **The classifier has its own test suite** (`python -m pytest tests/` — 10 passed) pinning the decision logic, including the sampling-error guards.

## What we learned

Cheap state forking isn't a convenience feature — it **changes which experiments are possible**. Deterministic replay has existed for years but is too heavy for routine CI use. Sandbox forking gets a large fraction of the causal signal at a tiny fraction of the cost.

We also learned to be disciplined about where the LLM sits in the pipeline. Our first instinct was to let the model classify the flake. Making classification mechanical and reserving the model for explanation made the system both more accurate and far easier to trust.

## What's next

- **CI integration**: run on changed tests per-PR, comment the signature, class, and patch.
- **Finer fork-point granularity** — per-fixture and per-test-phase checkpoints to narrow the entropy window from a phase to a line.
- **Real-world validation** against known-flaky tests in large open-source projects.
- **Flake regression gating**: fail a PR that introduces a `DDD` test.

## Feedback for Nebius / NVIDIA

*(Required field — "Most Valuable Feedback" is a real prize. Fill in from your own live run; starter notes below.)*

- **Sandboxes Beta gating is invisible until runtime.** The Sandboxes panel appears in the console sidebar and `contree-sdk` installs and authenticates fine, but the first `run()` returns `ForbiddenError`. Surfacing entitlement in the console (or failing at client construction with a clear "request Beta access" message) would save developers from building against an API they cannot execute.
- **Reasoning models need a documented token-budget contract.** Nemotron tiers spend a large, variable share of `max_tokens` on `reasoning_content` before emitting the answer. When the budget is tight the JSON payload is truncated mid-string with `finish_reason: "stop"` — indistinguishable from a clean completion. Documenting a recommended headroom for structured output, or exposing a separate reasoning budget, would save every agent developer this exact debugging session.
- **Model IDs in the catalog use inconsistent casing** (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` vs `nvidia/nemotron-3-super-120b-a12b`). A canonical, copy-pasteable list per tier would prevent a class of silent 404s.
- **Sandboxes' branching is under-marketed as a *measurement* primitive.** The docs frame forking around safety and parallel exploration. Identical-state replication as a way to *isolate nondeterminism* is a distinct, powerful use case that isn't documented anywhere.
- Clearer SDK documentation on exactly what execution state a fork captures (page cache, open FDs, thread state, RNG) would make methods like ours much easier to reason about rigorously.
- Nemotron's Nano/Super/Ultra split maps cleanly onto agent workloads; a cookbook on tier routing would be genuinely useful.
- _(Add specific observations from your own run — concrete detail is what wins this category.)_

## Built with
`nebius-token-factory` · `nebius-sandboxes` · `nvidia-nemotron` · `contree-sdk` · `python` · `fastapi` · `server-sent-events`

## Try it out
- **Live demo:** https://heisenbug-aditya-mehras-projects.vercel.app
- **GitHub:** https://github.com/matricphase-dot/heisenbug

The hosted demo replays a real session captured against live Nemotron models on Nebius Token Factory — every number, analysis and patch shown is genuine output, not a mock. Heisenbug spawns 36 parallel pytest processes per run, which exceeds serverless execution limits, so the hosted build replays rather than re-executes. `git clone` + `python -m uvicorn backend.server:app` runs the real thing.
