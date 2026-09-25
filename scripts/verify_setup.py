#!/usr/bin/env python3
"""Verify Nebius Token Factory setup before the live run.

Run this the moment your credits land:

    export NEBIUS_API_KEY=...
    python scripts/verify_setup.py

It answers the three questions that decide whether the live demo works:
  1. Does the API key authenticate?
  2. Which NVIDIA Nemotron models actually exist on this account?
  3. Do the IDs configured in backend/config.py resolve?

Exits non-zero if anything is wrong, and prints the exact export lines to fix it.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _load_dotenv() -> None:
    """Load .env from the project root so keys never need to be pasted around."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, ".env")
    if not os.path.exists(path):
        return
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v and not os.environ.get(k.strip()):
                os.environ[k.strip()] = v


_load_dotenv()

KEY = os.environ.get("NEBIUS_API_KEY", "")
BASE = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")


def main() -> int:
    if not KEY:
        print("✗ NEBIUS_API_KEY is not set.")
        print("  Get one at https://tokenfactory.nebius.com/ then:")
        print("    export NEBIUS_API_KEY=...")
        return 1

    try:
        from openai import OpenAI
    except ImportError:
        print("✗ openai SDK missing.  pip install -r requirements.txt")
        return 1

    client = OpenAI(api_key=KEY, base_url=BASE)

    # ---- 1. auth + model discovery ---------------------------------------
    print(f"→ Listing models at {BASE}")
    try:
        models = [m.id for m in client.models.list().data]
    except Exception as exc:
        print(f"✗ Could not list models: {exc}")
        print("  Check the key is a Token Factory key (AI Studio keys expired 2026-01-31)")
        return 1

    print(f"✓ Authenticated. {len(models)} models visible.\n")

    nemotron = sorted(m for m in models if "nemotron" in m.lower())
    nvidia = sorted(m for m in models if m.lower().startswith("nvidia/"))

    print("NVIDIA / Nemotron models available to you:")
    for m in (nemotron or nvidia):
        print(f"   {m}")
    if not (nemotron or nvidia):
        print("   (none found — the hackathon REQUIRES an NVIDIA open source model)")

    # ---- 2. check configured IDs -----------------------------------------
    from backend import config

    configured = {
        "HB_MODEL_NANO": config.MODEL_NANO,
        "HB_MODEL_SUPER": config.MODEL_SUPER,
        "HB_MODEL_ULTRA": config.MODEL_ULTRA,
    }

    print("\nConfigured model IDs:")
    bad = {}
    for env, mid in configured.items():
        ok = mid in models
        print(f"   {'✓' if ok else '✗'} {env:15s} {mid}")
        if not ok:
            bad[env] = mid

    # ---- 3. live smoke test ----------------------------------------------
    probe = next((m for m in (nemotron or nvidia) if m in models), None)
    if probe:
        print(f"\n→ Smoke test against {probe}")
        try:
            r = client.chat.completions.create(
                model=probe,
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=16, temperature=0,
            )
            print(f"✓ Inference works: {r.choices[0].message.content!r}")
        except Exception as exc:
            print(f"✗ Inference failed: {exc}")
            return 1

    if bad:
        print("\n⚠ Some configured IDs do not exist on this account.")
        print("  Pick the closest matches above and export them, e.g.:")
        for env in bad:
            suggestion = _suggest(env, nemotron or nvidia)
            if suggestion:
                print(f"    export {env}={suggestion}")
        print("\n  Then re-run this script.")
        return 1

    print("\n✓ All good. Heisenbug will use real Nemotron on Token Factory.")
    print("  Optional: export TAVILY_API_KEY=... (from the Builders Program)")
    return 0


def _suggest(env: str, candidates: list[str]) -> str | None:
    """Best-effort tier matching: nano -> smallest, ultra -> largest."""
    if not candidates:
        return None
    tier = env.split("_")[-1].lower()
    for c in candidates:
        if tier in c.lower():
            return c
    return candidates[0]


if __name__ == "__main__":
    sys.exit(main())
