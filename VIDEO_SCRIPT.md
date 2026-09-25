# Heisenbug — 3-Minute Demo Video Script

**Hard rules:** ≤3 min, public YouTube, audio must explicitly name **Nebius Token Factory** and **NVIDIA Nemotron**. Both are in the spoken lines below — do not cut them.

**Total: 2:55.**

---

### [0:00 – 0:20] — The universal pain

**SCREEN:** A CI dashboard or terminal. `pytest` — a test fails. Run again — it passes. Run again — fails.

**VO:**
> Every engineer watching this has done the following. A test fails in CI. You hit retry. It passes. You move on with your life.
>
> The standard tool for this is running the suite a hundred times. And it answers exactly one question: how *often* does it fail. It never tells you *why*.

---

### [0:20 – 0:45] — Why re-running can't work

**SCREEN:** Simple diagram — 100 arrows from 100 *different* starting states.

**VO:**
> Here's the reason, and it's structural. Every one of those hundred re-runs starts from a **different state**. Different process ID, different hash seed, different clock, different page cache.
>
> So when you see "failed twelve out of a hundred," you've measured a frequency. You have learned nothing about the mechanism. You cannot fix what you cannot localise.

---

### [0:45 – 1:15] — The insight

**SCREEN:** Heisenbug UI, idle. Highlight the thesis banner.

**VO:**
> **Nebius Token Factory Sandboxes** can fork live execution state. That makes a different experiment possible.
>
> Instead of a hundred runs from a hundred states — take **one** checkpoint, and launch twelve replicas from it. Byte-identical state. Same memory, same seed, same everything. Then ask: do they *still* disagree?
>
> If they do, the randomness is **live** — it's happening during execution. Thread scheduling, the wall clock, real I/O. If they agree, but they disagreed when we forked earlier, then the randomness was **baked in before that point** — a hash seed, a PID.
>
> That's not a statistic anymore. That's a controlled experiment.

---

### [1:15 – 2:00] — The live run *(money shot)*

**SCREEN:** Click **Hunt flaky tests**. Let the matrix fill column by column. Do not speed up.

**VO:**
> Five tests. Watch the matrix fill in.
>
> First fork point, before the interpreter starts: three tests diverge.
>
> Second fork point, after startup — and look at `test_tag_ordering`. It goes **stable**. Twelve out of twelve replicas now agree. That's the proof: its randomness was the hash seed, fixed at startup.
>
> But `test_concurrent_counter` and `test_cache_timestamp` **keep diverging**, even from byte-identical state, all the way to the last fork point. Their entropy is live.

**[PAUSE on the signature column.]**

> D-S-S. D-D-D. D-D-D. Three flaky tests, mechanically separated into two different causes.

---

### [2:00 – 2:30] — Why it matters

**SCREEN:** Scroll to the finding cards showing the different patches.

**VO:**
> Here's why that distinction is the whole product. On a retry dashboard, all three of these look **identical** — they're just "sometimes fails."
>
> But the fixes are mutually wrong. Pinning a seed does *nothing* for a thread race. Adding a lock does *nothing* for hash ordering.
>
> So the classification is mechanical — it comes from execution evidence and statistics, not from a model's opinion. Then **NVIDIA Nemotron**, served on Nebius Token Factory, explains each one and writes the patch appropriate to *its* class. A lock for the race. A clock seam for the timestamp. An explicit sort for the hash ordering.

---

### [2:30 – 2:40] — Real repositories

**SCREEN:** Switch the dropdown to `● real repo · grantjenks/python-diskcache`. Show it cloning and sweeping.

**VO:**
> And this isn't only a toy. Point it at a real repository — here's diskcache, a widely-deployed caching library. Heisenbug clones it, installs it, and sweeps ninety-two real tests. It reports them **clean**. Which matters: a flake detector that can't say "nothing here" isn't one you can trust when it does find something.

---

### [2:40 – 2:55] — Rigour and close

**SCREEN:** Hover a verdict to show the statistical note. Then the full matrix.

**VO:**
> And it knows when it doesn't know. A test failing forty percent of the time can look unanimous by pure chance — so Heisenbug computes that probability, and when the evidence is marginal it forks **more** replicas instead of guessing.
>
> Thirty-six suite runs. Three flaky tests. Two distinct causes, proven — not estimated.
>
> Heisenbug. Built on **Nebius Sandboxes** and **NVIDIA Nemotron**.

---

## Production checklist

- [ ] Do a few dry runs; confirm `test_tag_ordering` shows `DSS` and the other two show `DDD`. (Verified 10/10, but check your machine.)
- [ ] Pre-warm the diskcache clone before recording (first run pays clone + pip install, ~40s). Run it once, then record the second run so the sweep starts promptly.
- [ ] 1920×1080, browser zoom ~110% so the matrix is legible after compression.
- [ ] **Do not time-lapse the matrix filling.** Watching `DSS` emerge column by column is the proof.
- [ ] Record VO separately; lay over screen capture.
- [ ] Say "Nebius Token Factory" and "NVIDIA Nemotron" clearly — required in **audio**.
- [ ] Upload **Public**.
- [ ] Title: `Heisenbug — proving why tests are flaky | Nebius x NVIDIA Global AI Hackathon`
- [ ] Pin a comment with the GitHub link.

## Delivery note

The 0:00–0:45 stretch is pure problem-setting with no product on screen. That's deliberate — the insight only lands if the audience first feels *why* re-running can't work. Don't rush it, and don't cut to the UI early.
