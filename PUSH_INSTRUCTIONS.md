# Pushing Heisenbug to GitHub

The repo is already initialised and committed here. You just need to create the
remote and push.

---

## 1. Create an empty repo on GitHub

Go to **https://github.com/new**

- **Repository name:** `heisenbug`
- **Description:** `Classify flaky tests by cause, not frequency — differential execution over forked sandbox state. Nebius Token Factory + NVIDIA Nemotron.`
- **Public** ← required by the hackathon rules
- **Do NOT** tick "Add a README", "Add .gitignore", or "Choose a license"
  (we already have all three — ticking them causes a merge conflict)

Click **Create repository**.

---

## 2. Push

Copy your files out of the sandbox first if you're working locally, or run these
from wherever the project lives. Replace `YOUR_USERNAME`:

```bash
cd heisenbug
git remote add origin https://github.com/YOUR_USERNAME/heisenbug.git
git branch -M main
git push -u origin main
```

If GitHub asks for a password, it wants a **Personal Access Token**, not your
account password:
→ https://github.com/settings/tokens → *Generate new token (classic)* → tick
**repo** scope → copy it → paste as the password.

---

## 3. Verify the submission requirements

After pushing, check the repo page shows:

- [ ] **Apache-2.0** badge in the right-hand sidebar (the rules require a visible
      OSS license at the top of the repo page)
- [ ] README renders with the divergence-signature table
- [ ] **`.env` is NOT in the file list** ← confirm this by eye

If `.env` ever appears, your API key is public. Rotate it immediately at
https://tokenfactory.nebius.com/ → API keys.

---

## 4. Add repo topics (helps judges find it)

On the repo page, click the gear next to *About* and add:

```
nebius  nvidia  nemotron  flaky-tests  testing  ai-agents  python  hackathon
```

---

## Already handled for you

- `.gitignore` excludes `.env`, `__pycache__/`, `*.pyc`, `.pytest_cache/`
- `.env.example` documents which keys are needed, with no values
- Apache 2.0 `LICENSE` at the repo root
- Commit message explains the method for anyone landing cold
- Staged content scanned — no key material committed
