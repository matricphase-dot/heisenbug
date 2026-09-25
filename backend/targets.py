"""Target definitions: point Heisenbug at any repository.

A target tells the executor how to materialise a repo, install it, and run a
subset of its suite. The bundled demo target is self-contained; the real-repo
targets clone actual open-source projects.

Everything Heisenbug does is repo-agnostic — the divergence sweep, the
classifier, and the statistics never look at which project they are running.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Target:
    key: str
    name: str
    description: str
    # Either a local path (bundled) or a git URL to clone.
    local_path: str | None = None
    git_url: str | None = None
    git_ref: str | None = None
    install: list[str] = field(default_factory=list)
    pytest_args: list[str] = field(default_factory=list)
    # Files shown in the UI / handed to Nemotron for patch synthesis.
    source_files: list[str] = field(default_factory=list)
    notes: str = ""


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEMO = Target(
    key="demo",
    name="Bundled demo suite",
    description=(
        "Three deliberately distinct entropy sources (hash seed, thread race, wall "
        "clock) plus two deterministic controls. Ground truth is known, so this "
        "target verifies the classifier end to end."
    ),
    local_path=os.path.join(ROOT, "flaky_repo"),
    pytest_args=["tests/test_service.py"],
    source_files=["tests/test_service.py"],
)

DISKCACHE = Target(
    key="diskcache",
    name="grantjenks/python-diskcache",
    description=(
        "A real, widely-deployed caching library (SQLite-backed). Its recipes module "
        "implements cross-process locks, semaphores and throttles, and several tests "
        "assert on millisecond-scale expiry — genuine wall-clock and concurrency "
        "surface."
    ),
    git_url="https://github.com/grantjenks/python-diskcache.git",
    install=["pip", "install", "-q", "-e", "."],
    pytest_args=["tests/test_recipes.py", "tests/test_core.py", "-o", "addopts="],
    source_files=["tests/test_recipes.py", "diskcache/recipes.py"],
    notes=(
        "Upstream documents load-dependence explicitly: the throttle() doctest "
        "asserts `count in (6, 7)` with the comment '6 or 7 calls depending on CPU "
        "load'. Heisenbug's job is to decide, from execution evidence, whether the "
        "suite's nondeterminism is live or seeded."
    ),
)

TENACITY = Target(
    key="tenacity",
    name="jd/tenacity",
    description=(
        "A retry library whose tests exercise real sleeps, deadlines and async "
        "scheduling — wall-clock dependent by construction."
    ),
    git_url="https://github.com/jd/tenacity.git",
    install=["pip", "install", "-q", "-e", "."],
    pytest_args=["tests/test_tenacity.py", "-o", "addopts="],
    source_files=["tests/test_tenacity.py"],
)

TARGETS = {t.key: t for t in (DEMO, DISKCACHE, TENACITY)}


def get(key: str) -> Target:
    return TARGETS.get(key, DEMO)
