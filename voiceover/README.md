# Heisenbug — Narration Audio

Six pre-recorded voiceover segments matching `../VIDEO_SCRIPT.md`.
**Total runtime 2:50** — 10 seconds under the hackathon's 3:00 limit.

| # | File | Duration | Cue in | What's on screen |
|---|------|---------:|-------:|------------------|
| 1 | `01_cold_open.mp3` | 17.6s | 0:00 | Terminal: pytest fails, passes, fails |
| 2 | `02_why_rerunning_fails.mp3` | 20.0s | 0:17 | Diagram: 100 runs from 100 different states |
| 3 | `03_the_insight.mp3` | 36.2s | 0:37 | Heisenbug UI idle, thesis banner readable |
| 4 | `04_live_run.mp3` | 42.3s | 1:13 | **Click Replay.** Matrix fills column by column |
| 5 | `05_why_it_matters.mp3` | 32.2s | 1:56 | Scroll the three finding cards / patches |
| 6 | `06_close.mp3` | 21.7s | 2:28 | Hover a verdict note, then full matrix |

`full_narration.mp3` is all six concatenated. Note: its *duration metadata* reads
incorrectly (raw MP3 concatenation has no Xing header) — the audio is complete and
plays fine, but **import the six separate files instead**. You want them separate
anyway so each cue can be nudged against its visual beat.

## How to assemble the video

1. **Screen-record** https://heisenbug-aditya-mehras-projects.vercel.app at 1920×1080,
   browser zoom ~110%. Capture one clean replay (~14s) plus slow scrolls through the
   findings cards. Record more footage than you need.
2. **Drop the six audio files** onto the timeline in order, back to back.
3. **Trim/stretch the video** under each segment to match. The only hard sync point is
   segment 4: the narration says *"it goes stable"* around 0:18 into that clip, so the
   `post_import` column should already be visible by then.
4. Segments 1–3 are talking-head-free setup — use the terminal clip, a simple diagram,
   and the idle UI. Nothing needs to be frame-accurate.
5. Export 1080p, upload **Public** to YouTube.

Free editors that handle this in minutes: DaVinci Resolve, CapCut, Clipchamp (built into
Windows), or Canva.

## Timing safety

Continuous speech is 170s. You have 10s of slack for gaps between segments — keep any
pauses under ~1.5s each and you'll land comfortably under 3:00. Do not add a long
intro card; the rules cap total runtime, not just narration.

## If you'd rather record your own voice

Use `../VIDEO_SCRIPT.md` as the read script. It's paced at 1.9–2.9 words/second per
section, which is comfortable narration speed. Both required phrases — "Nebius Token
Factory" and "NVIDIA Nemotron" — are already in the spoken lines and must stay in the
audio, not just on screen.
