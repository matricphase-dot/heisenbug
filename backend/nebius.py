"""Nebius Token Factory chat client (OpenAI-compatible) + offline demo stub."""

from __future__ import annotations

import json
import re
from typing import Any

from . import config

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=config.NEBIUS_API_KEY, base_url=config.BASE_URL)
    return _client


def chat(model: str, system: str, user: str,
         temperature: float = 0.2, max_tokens: int = 3000) -> str:
    if config.DEMO_MODE:
        return _demo(system, user)
    resp = _get_client().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        temperature=temperature, max_tokens=max_tokens,
    )
    return resp.choices[0].message.content or ""


def chat_json(model: str, system: str, user: str,
              temperature: float = 0.2, max_tokens: int = 4000) -> dict[str, Any]:
    """Chat + JSON parse, retrying once with more headroom on truncation.

    Nemotron reasoning tiers emit `reasoning_content` before the answer, so a
    tight budget truncates the payload. One retry with a larger budget and an
    explicit brevity instruction recovers essentially all remaining cases.
    """
    last: Exception | None = None
    for attempt, budget in enumerate((max_tokens, max_tokens * 2)):
        sys_msg = system if attempt == 0 else (
            system + "\n\nIMPORTANT: reply with the JSON object only. "
            "Keep every field under 60 words. Do not think out loud."
        )
        try:
            return extract_json(chat(model, sys_msg, user, temperature, budget))
        except Exception as exc:
            last = exc
    raise last if last else ValueError("no response")


def extract_json(text: str) -> dict[str, Any]:
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in response")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc: esc = False
            elif c == "\\": esc = True
            elif c == '"': in_str = False
            continue
        if c == '"': in_str = True
        elif c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])

    # Reasoning models spend tokens on chain-of-thought before the answer, so a
    # token budget can truncate the JSON mid-object. Rather than discard a
    # response that is 95% complete, close the open string/braces and salvage it.
    salvaged = text[start:]
    if in_str:
        salvaged += '"'
    salvaged += "}" * depth
    try:
        return json.loads(salvaged)
    except Exception:
        pass
    raise ValueError("unbalanced JSON")


# ---------------------------------------------------------------------------
# Offline stub — keyed off the classifier verdict present in the prompt.
# ---------------------------------------------------------------------------

_FIX_COUNTER = {
    "summary": (
        "Four threads execute a read-modify-write on a shared module-level counter "
        "with an explicit yield between the read and the write. The interleaving is "
        "decided by the OS scheduler, which is live in every replica regardless of "
        "where the fork is taken — so lost updates occur nondeterministically."
    ),
    "repro": "pytest tests/test_service.py::test_concurrent_counter (run under load; ~1 in 3)",
    "patch": (
        "import threading\n"
        "_lock = threading.Lock()\n\n"
        "def _bump():\n"
        "    global _counter\n"
        "    for _ in range(200):\n"
        "        with _lock:            # make the read-modify-write atomic\n"
        "            _counter += 1\n"
    ),
}

_FIX_CLOCK = {
    "summary": (
        "The assertion is a predicate over the current wall clock, so its truth value "
        "changes between replicas even from identical state. The clock is an "
        "uncontrolled external input."
    ),
    "repro": "pytest tests/test_service.py::test_cache_timestamp (fails whenever ms % 3 == 0)",
    "patch": (
        "def test_cache_timestamp(monkeypatch):\n"
        "    # Inject a fixed clock instead of asserting on live time.\n"
        "    monkeypatch.setattr(time, \"time\", lambda: 1_700_000_000.001)\n"
        "    t = time.time()\n"
        "    assert int(t * 1000) % 3 != 0\n"
    ),
}

_FIX_HASH = {
    "summary": (
        "The test asserts on the iteration order of a set literal. Set ordering is a "
        "function of PYTHONHASHSEED, which is chosen once at interpreter startup — "
        "which is exactly why divergence vanishes when replicas are forked after "
        "startup. The test encodes an incidental ordering as a contract."
    ),
    "repro": "PYTHONHASHSEED=random pytest tests/test_service.py::test_tag_ordering",
    "patch": (
        "def test_tag_ordering():\n"
        "    tags = {\"alpha\", \"beta\", \"gamma\", \"delta\", \"epsilon\"}\n"
        "    # Assert on a defined order, not on incidental hash ordering.\n"
        "    assert sorted(tags)[0] == \"alpha\"\n"
    ),
}


def _demo(system: str, user: str) -> str:
    s, u = system.lower(), user
    if "final report" in s or "causal" in s:
        return (
            "Three distinct entropy sources are present in this suite, and the fork-point "
            "sweep separates them cleanly.\n\n"
            "test_tag_ordering is startup-seeded: it diverges when replicas fork before "
            "interpreter start and is perfectly stable afterwards, which localises the "
            "entropy to hash-seed selection. Pinning or sorting is a complete fix.\n\n"
            "test_concurrent_counter and test_cache_timestamp are true runtime "
            "nondeterminism: they keep diverging even from byte-identical state at the "
            "latest fork point, proving the entropy is live during execution — the "
            "scheduler and the wall clock respectively. No amount of seeding will "
            "stabilise them; they need a lock and a clock seam.\n\n"
            "Operationally this matters because the three would look identical on a CI "
            "retry dashboard — all just 'flaky' — yet two of the three fixes are wrong "
            "for the other class."
        )
    # Match on the TEST: header line only — the full file source mentions every
    # test name, so substring matching over the whole prompt would misfire.
    head = ""
    for line in u.splitlines():
        if line.startswith("TEST: "):
            head = line
            break
    if "concurrent_counter" in head:
        return json.dumps(_FIX_COUNTER)
    if "cache_timestamp" in head:
        return json.dumps(_FIX_CLOCK)
    if "tag_ordering" in head:
        return json.dumps(_FIX_HASH)
    return json.dumps({
        "summary": "No nondeterminism detected from identical state.",
        "repro": "n/a", "patch": "",
    })
