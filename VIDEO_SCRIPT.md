# Heisenbug — 3-Minute Demo Video Script

**Hard rules:** ≤3 min, public YouTube, audio must explicitly name **Nebius Token Factory** and **NVIDIA Nemotron**. Both are in the spoken lines below — do not cut them.

**Total: 2:51.** 9 seconds of headroom.

**Narration audio is already recorded** — see `voiceover/` (six MP3 segments, 2:50 total,
10s under the limit). You only need to screen-record and lay the audio over it. Full
assembly instructions in `voiceover/README.md`.

**Record against:** https://heisenbug-aditya-mehras-projects.vercel.app (replays a real captured run — reliable, no cold start, ~14s) or your local live server. Either works; the deployed one is safer.

---

### [0:00 – 0:20] — The universal pain

**SCREEN:** A terminal. `pytest` — a test fails. Run again — it passes. Run again — fails.

**VO:**
> Every engineer watching this has done the following. A test fails in CI. You hit retry. It passes. You move on with your life.
>
> The standard tool for this is running the suite a hundred times. And it answers exactly one question: how *often* does it fail. It never tells you *why*.

---

### [0:20 – 0:45] — Why re-running can't work

**SCREEN:** Simple diagram — 100 arrows starting from 100 *different* states.

**VO:**
> Here's the reason, and it's structural. Every one of those hundred re-runs starts from a **different state**. Different process ID, different hash seed, different clock, different page cache.
>
> So when you see "failed twelve out of a hundred," you've measured a frequency. You've learned nothing about the mechanism. You can't fix what you can't localise.

---

### [0:45 – 1:15] — The insight

**SCREEN:** Heisenbug UI, idle. Let the thesis banner be readable.

**VO:**
> **Nebius Token Factory Sandboxes** can fork live execution state. That makes a different experiment possible.
>
> Instead of a hundred runs from a hundred states — take **one** checkpoint, and launch twelve replicas from it. Byte-identical state. Same memory, same seed, same everything. Then ask: do they *still* disagree?
>
> If they do, the randomness is **live** — it's happening during execution. Thread scheduling, the wall clock, real I/O. If they agree, but they disagreed when we forked earlier, then the randomness was **baked in before that point** — a hash seed, a process ID.
>
> That's not a statistic anymore. That's a controlled experiment.

---

### [1:15 – 2:00] — The run *(money shot)*

**SCREEN:** Click the button. Let the matrix fill column by column. **Do not speed this up.**

**VO:**
> Five tests. Watch the matrix fill in.
>
> First fork point, before the interpreter starts — three tests diverge.
>
> Second fork point, after startup. And look at `test_tag_ordering`. It goes **stable**. Twelve out of twelve replicas now agree. That's the proof: its randomness was the hash seed, fixed once at startup.
>
> But `test_concurrent_counter` and `test_cache_timestamp` **keep diverging** — even from byte-identical state, all the way to the last fork point. Their entropy is live.

**[PAUSE on the signature column.]**

> D-S-S. D-D-D. D-D-D. Three flaky tests, mechanically separated into two different causes.

---

### [2:00 – 2:32] — Why it matters

**SCREEN:** Scroll through the three finding cards, showing the different patches side by side.

**VO:**
> Here's why that distinction is the whole product. On a retry dashboard, all three look **identical**. They're just "sometimes fails."
>
> But the fixes are mutually wrong. Pinning a seed does *nothing* for a thread race. A lock does *nothing* for hash ordering.
>
> So the classification is mechanical — execution evidence, not a model's opinion. Then **NVIDIA Nemotron**, on **Nebius Token Factory**, writes the patch appropriate to *its* class.
>
> A lock for the race. A mocked clock for the timestamp. A sort for the hash ordering.

---

### [2:32 – 2:51] — Rigour and close

**SCREEN:** Hover a verdict to surface the statistical note. Then the full matrix, full frame.

**VO:**
> And it knows when it doesn't know. A rare failure can look unanimous by chance — so when the evidence is marginal, Heisenbug forks **more** replicas instead of guessing.
>
> Thirty-six suite runs. Two distinct causes — proven, not estimated.
>
> Heisenbug. Built on **Nebius Sandboxes** and **NVIDIA Nemotron**.

---

## Production checklist

- [ ] Record at **1920×1080**, browser zoom ~110% so the matrix and log text survive YouTube compression.
- [ ] Hide bookmarks bar, clean browser profile, dark OS theme.
- [ ] **Do not time-lapse the matrix filling.** Watching `DSS` emerge column by column is the proof.
- [ ] Record VO separately and lay it over the screen capture. Phone earbuds in a quiet room beat a laptop mic.
- [ ] Say "Nebius Token Factory" and "NVIDIA Nemotron" clearly — the rules require it in the **audio**, not just on screen.
- [ ] Upload **Public** (not Unlisted).
- [ ] Title: `Heisenbug — proving why tests are flaky | Nebius x NVIDIA Global AI Hackathon`
- [ ] Pin a comment with the repo link: `https://github.com/matricphase-dot/heisenbug`

## Delivery notes

**Don't rush the opening.** 0:00–0:45 is pure problem-setting with no product on screen. That's deliberate — the insight only lands if the audience first feels *why* re-running can't work. Cutting to the UI early kills the payoff.

**The pause at 1:50 matters.** Let `DSS` sit on screen for a beat before you say it. The visual should arrive before the explanation.

**If you run over 3:00**, cut the architecture explanation at 0:45–1:15 down to two sentences. The live matrix is worth more than the setup.
