# Submission checklist

Everything below was verified on 2026-09-25. Work top to bottom.

---

## ⚠️ First: you are submitting to the WRONG hackathon if the URL says "shipaton"

Correct page → **https://nebiusglobalaihackathon.devpost.com/**
Deadline: **Oct 30, 2026, 10:00 AM PT** (RevenueCat Shipaton is a different event, Oct 1.)

---

## 1. Upload the video

File: `video/heisenbug_demo.mp4` — 2:50, 1920×1080 @30fps, H.264 + AAC, 17 MB.

- [ ] YouTube → Upload → set visibility **Public** (not Unlisted — the rules say public)
- [ ] Title: `Heisenbug — proving why tests are flaky | Nebius x NVIDIA Global AI Hackathon`
- [ ] Pin a comment with `https://github.com/matricphase-dot/heisenbug`
- [ ] Copy the watch URL

## 2. Create the Devpost project

- [ ] https://nebiusglobalaihackathon.devpost.com/ → **My projects** → **Create project**

| Field | Value |
|---|---|
| Name | `Heisenbug` |
| Tagline | Top line of `SUBMISSION.md` |
| **Track** | **Coding and Agentic Engineering** ← easy to miss |
| Video | your YouTube URL |
| Try it out #1 | `https://heisenbug-aditya-mehras-projects.vercel.app` |
| Try it out #2 | `https://github.com/matricphase-dot/heisenbug` |
| Description | Everything from "Inspiration" down in `SUBMISSION.md` |
| Built with | `nebius-token-factory` `nvidia-nemotron` `contree-sdk` `python` `fastapi` `server-sent-events` |
| Feedback field | The "Feedback for Nebius / NVIDIA" section |

- [ ] City field: leave blank (no India Builders & Brews event was held)

## 3. Send the Sandboxes access request

- [ ] Post `SANDBOXES_ACCESS.md` in Discord (https://discord.gg/ZdC3rXMJH) or email contree@nebius.com
- [ ] If granted before Oct 30: `python video/record.py 04_live_run && python video/assemble.py`,
      re-upload, update the Devpost video link

## 4. Security — do this now, not later

- [ ] Revoke GitHub token → https://github.com/settings/tokens (`ghp_QFoC...`, has full `repo` scope)
- [ ] Revoke Vercel token → https://vercel.com/account/tokens (`vcp_1v0W...`)
- [ ] Rotate Nebius API key → https://tokenfactory.nebius.com/ → API keys

All three were pasted into a chat transcript. Everything is already deployed, so revoking
breaks nothing.

---

## Verified state (re-checked 2026-09-25)

| Check | Result |
|---|---|
| Classifier correctness, 3 consecutive runs | PASS — 36 suite runs each |
| `pytest tests/` | 10 passed |
| Hosted demo, headless DOM (local build) | PASS — 5 rows, 3 cards, 1 report, 0 JS errors |
| Hosted demo, headless DOM (live site) | PASS — identical |
| Video duration / resolution / audio | 2:50 · 1920×1080 · AAC stereo, −22 dB mean, no silent gaps |
| GitHub repo | HTTP 200, Apache-2.0 detected, public |
| `.env` exposure | HTTP 404 — never committed |
| Nemotron model IDs | all 3 resolve and return completions |
| Sandboxes | 403 — missing Beta role, documented, falls back cleanly |

## Reproducing the checks

```bash
python -m pytest tests/ -q                    # classifier logic
node tests/test_web_replay.js --live          # hosted demo actually renders
python scripts/verify_setup.py                # Nemotron + Sandboxes entitlement
```
