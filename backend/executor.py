"""Differential execution backends.

Heisenbug's whole thesis rests on one operation that only Nebius Sandboxes
provide cheaply:

    replicate(fork_point, n) -> n test runs launched from BYTE-IDENTICAL state

Classical flaky-test hunting re-runs a suite N times, but every re-run starts
from a *different* initial state (fresh PID, fresh hash seed, fresh clock,
fresh page cache). So "failed 12/100" tells you a test is flaky but nothing
about *why*.

Forking gives us the missing experiment. If we snapshot execution at a point
and launch N replicas from that exact snapshot, then any divergence between
replicas is proof that the entropy source is LIVE at that point (thread
scheduling, wall clock, real I/O) rather than having been fixed earlier
(hash seed, env, PID, RNG seed).

Sweeping the fork point from early to late and watching WHERE divergence
disappears localises the entropy source in time. That is the bisection.
"""

from __future__ import annotations

import collections
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import config

_RESULT = re.compile(r"(tests/\S+?)::(\S+?)\s+(PASSED|FAILED|ERROR)")


@dataclass
class RunOutcome:
    """Per-test PASSED/FAILED map for one replica."""
    results: dict[str, str] = field(default_factory=dict)
    stdout: str = ""
    replica: int = 0


def parse_verbose(output: str) -> dict[str, str]:
    out = {}
    for _file, test, status in _RESULT.findall(output):
        out[test] = status
    return out


# Environment knobs that emulate each fork point for the local backend.
# pre_interpreter : nothing is fixed yet -> hash seed varies per replica
# post_import     : interpreter is up, hash seed already burned in -> fixed
# post_fixture    : module state also materialised -> fixed
_FORK_ENV = {
    "pre_interpreter": None,        # randomise
    "post_import": "20260918",      # frozen snapshot value
    "post_fixture": "20260918",
}


class NebiusForkExecutor:
    """Replicate test runs from identical Sandbox checkpoints."""

    name = "nebius-sandboxes"

    def __init__(self, repo_dir: str, target=None):
        from contree_sdk import ContreeSync

        self.repo_dir = repo_dir
        self.target = target
        self._pytest_args = list(getattr(target, "pytest_args", []) or [])
        self.client = ContreeSync()
        self._checkpoints: dict[str, object] = {}

    def prepare(self) -> None:
        image = self.client.images.use(config.SANDBOX_IMAGE)
        session = image.session()
        t = self.target
        if t is not None and getattr(t, "git_url", None):
            session.run("sh", args=["-c",
                f"apt-get update -qq && apt-get install -y -qq git && "
                f"git clone --depth 1 {t.git_url} /app"]).wait()
            if t.install:
                session.run("sh", args=["-c",
                    "cd /app && " + " ".join(t.install)]).wait()
        else:
            session.rsync(source=self.repo_dir, destination="/app",
                          exclude=["__pycache__", ".git", ".venv", ".pytest_cache"])
        session.run("pip", args=["install", "-q", "pytest"]).wait()
        self._base = session

        # Materialise one checkpoint per fork point along the timeline.
        for fp in config.FORK_POINTS:
            s = self._base.fork()
            if fp != "pre_interpreter":
                # Advance execution past interpreter start / imports so that
                # startup-seeded entropy is already baked into the snapshot.
                s.run("sh", args=["-c",
                    "cd /app && python -c 'import sys; import tests' 2>/dev/null || true"]).wait()
            self._checkpoints[fp] = s

    def replicate(self, fork_point: str, n: int) -> list[RunOutcome]:
        base = self._checkpoints[fork_point]

        def one(i: int) -> RunOutcome:
            # Every replica forks the SAME checkpoint -> byte-identical state.
            child = base.fork()
            extra = " ".join(self._pytest_args)
            res = child.run("sh", args=[
                "-c", f"cd /app && python -m pytest -v --tb=no "
                      f"-p no:cacheprovider {extra}"
            ]).wait()
            text = (res.stdout or "") + (res.stderr or "")
            return RunOutcome(parse_verbose(text), text[-3000:], i)

        with ThreadPoolExecutor(max_workers=min(n, 16)) as pool:
            return list(pool.map(one, range(n)))

    def source(self, path: str) -> str:
        try:
            return self._base.cat(os.path.join("/app", path))
        except Exception:
            return ""


class LocalForkExecutor:
    """Local stand-in with the identical interface.

    Fork points are emulated with PYTHONHASHSEED: 'pre_interpreter' randomises
    it per replica (entropy not yet fixed), later fork points freeze it (the
    snapshot already captured it). Thread scheduling and the wall clock remain
    genuinely live in every replica, exactly as they would inside a sandbox.

    Real-repo targets are cloned once and installed once; every replica then
    runs the suite in its own copy so that on-disk state cannot leak between
    replicas and masquerade as nondeterminism.
    """

    name = "local-fork"

    def __init__(self, repo_dir: str, target=None):
        self.target = target
        self.root = tempfile.mkdtemp(prefix="heisenbug-")
        self.work = os.path.join(self.root, "base")
        self.repo_dir = repo_dir
        self._pytest_args = list(getattr(target, "pytest_args", []) or [])

    def prepare(self) -> None:
        t = self.target
        if t is not None and getattr(t, "git_url", None):
            subprocess.run(
                ["git", "clone", "--depth", "1", t.git_url, self.work],
                capture_output=True, text=True, timeout=600, check=True,
            )
            if t.install:
                subprocess.run(t.install, cwd=self.work, capture_output=True,
                               text=True, timeout=900)
        else:
            src = self.repo_dir
            shutil.copytree(src, self.work,
                            ignore=shutil.ignore_patterns(
                                "__pycache__", ".pytest_cache", ".git"))

    def replicate(self, fork_point: str, n: int) -> list[RunOutcome]:
        frozen = _FORK_ENV.get(fork_point)
        args = self._pytest_args or []

        def one(i: int) -> RunOutcome:
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = frozen if frozen else str(uuid.uuid4().int % 100000)
            # Give each replica an isolated scratch dir so that shared temp
            # state can never be mistaken for genuine nondeterminism.
            scratch = os.path.join(self.root, f"tmp{i}")
            os.makedirs(scratch, exist_ok=True)
            env["TMPDIR"] = scratch
            try:
                p = subprocess.run(
                    ["python", "-m", "pytest", "-v", "--tb=no",
                     "-p", "no:cacheprovider", *args],
                    cwd=self.work, capture_output=True, text=True,
                    env=env, timeout=900,
                )
                text = p.stdout + p.stderr
            except subprocess.TimeoutExpired:
                text = "TIMEOUT"
            return RunOutcome(parse_verbose(text), text[-3000:], i)

        with ThreadPoolExecutor(max_workers=min(n, 8)) as pool:
            return list(pool.map(one, range(n)))

    def source(self, path: str) -> str:
        try:
            with open(os.path.join(self.work, path)) as fh:
                return fh.read()
        except Exception:
            return ""


def make_executor(repo_dir: str, target=None):
    if config.DEMO_MODE:
        return LocalForkExecutor(repo_dir, target)
    try:
        return NebiusForkExecutor(repo_dir, target)
    except Exception as exc:  # pragma: no cover
        print(f"[heisenbug] Sandboxes unavailable ({exc}); using local executor")
        return LocalForkExecutor(repo_dir, target)


def divergence(outcomes: list[RunOutcome]) -> dict[str, dict]:
    """Per-test divergence across replicas launched from identical state."""
    tally: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for o in outcomes:
        for test, status in o.results.items():
            tally[test][status] += 1

    report = {}
    for test, c in tally.items():
        total = sum(c.values())
        failed = c.get("FAILED", 0) + c.get("ERROR", 0)
        passed = c.get("PASSED", 0)
        report[test] = {
            "failed": failed,
            "passed": passed,
            "total": total,
            "diverges": 0 < failed < total,
            "fail_rate": failed / total if total else 0.0,
        }
    return report
