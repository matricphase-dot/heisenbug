"""Heisenbug configuration: Nebius endpoints, Nemotron routing, probe budgets."""

import os


def _load_dotenv() -> None:
    """Load .env from the project root if present (never committed)."""
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
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if v and not os.environ.get(k):
                os.environ[k] = v


_load_dotenv()

NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
NEBIUS_PROJECT_ID = os.environ.get("NEBIUS_PROJECT_ID", "")

BASE_URL = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")

# --- NVIDIA Nemotron routing ----------------------------------------------
# Nano  : per-test evidence summarisation (runs once per flaky test, high volume)
# Super : repro-recipe + fix-patch synthesis
# Ultra : final causal report over the whole divergence matrix
MODEL_NANO = os.environ.get("HB_MODEL_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")
MODEL_SUPER = os.environ.get("HB_MODEL_SUPER", "nvidia/nemotron-3-super-120b-a12b")
MODEL_ULTRA = os.environ.get("HB_MODEL_ULTRA", "nvidia/Nemotron-3-Ultra-550b-a55b")

# --- Differential execution budget ----------------------------------------
# Replicas per fork point. Divergence is detected when a test is neither
# all-pass nor all-fail across replicas launched from BYTE-IDENTICAL state.
REPLICAS = int(os.environ.get("HB_REPLICAS", "12"))

# Fork points along the execution timeline, earliest -> latest.
# The classifier is driven by WHERE divergence stops.
FORK_POINTS = ["pre_interpreter", "post_import", "post_fixture"]

SANDBOX_IMAGE = os.environ.get("HB_IMAGE", "python:3.12-slim")

DEMO_MODE = not bool(NEBIUS_API_KEY)
