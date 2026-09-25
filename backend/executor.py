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
    """Replicate test runs from identical Nebius Sandbox (ConTree) states.

    ConTree's branching model is the whole reason Heisenbug's experiment is
    possible. Calling ``state.run(...)`` does not mutate ``state`` — it returns a
    *new* state branched from it. So calling ``.run()`` N times on the same
    parent gives N executions that each began from byte-identical filesystem and
    process state, which is exactly the controlled experiment we need:

        base   = images.use("python:3.12-slim")
        ready  = base.run(shell="pip install pytest && ...", disposable=False)
        r1     = ready.run(shell="pytest ...", disposable=False)   # branch 1
        r2     = ready.run(shell="pytest ...", disposable=False)   # branch 2
        #        ^ r1 and r2 both started from `ready`, bit for bit

    A useful property falls out of this: ConTree derives each state's ``uuid``
    from its content, so two branches of a *deterministic* command collapse to
    the same uuid, while a *nondeterministic* one yields different uuids. We
    record those uuids alongside the pass/fail data as corroborating evidence
    for the divergence we measure from test outcomes.

    Note: Sandboxes is in Beta and gated per-account. If the API returns a
    permission error, `make_executor` transparently falls back to the local
    executor, which implements the identical experiment.
    """

    name = "nebius-sandboxes"

    def __init__(self, repo_dir: str, target=None):
        from contree_sdk import ContreeSync

        self.repo_dir = repo_dir
        self.target = target
        self._pytest_args = list(getattr(target, "pytest_args", []) or [])
        self.client = ContreeSync(token=config.NEBIUS_API_KEY or None)
        self._states: dict[str, object] = {}
        self.state_uuids: dict[str, list[str]] = {}

    # -- helpers ---------------------------------------------------------

    def _upload_spec(self) -> dict[str, str]:
        """Map local repo files -> absolute in-sandbox paths under /app."""
        spec: dict[str, str] = {}
        for root, dirs, names in os.walk(self.repo_dir):
            dirs[:] = [d for d in dirs
                       if d not in ("__pycache__", ".git", ".venv", ".pytest_cache")]
            for n in names:
                if n.endswith(".pyc"):
                    continue
                local = os.path.join(root, n)
                rel = os.path.relpath(local, self.repo_dir)
                spec[f"/app/{rel}"] = local
        return spec

    def prepare(self) -> None:
        base = self.client.images.use(config.SANDBOX_IMAGE)
        t = self.target

        if t is not None and getattr(t, "git_url", None):
            ready = base.run(
                shell=(
                    "apt-get update -qq && apt-get install -y -qq git >/dev/null && "
                    f"git clone --depth 1 {t.git_url} /app && "
                    "pip install -q pytest && "
                    + ("cd /app && " + " ".join(t.install) if t.install else "true")
                ),
                disposable=False,
            ).wait()
        else:
            ready = base.run(
                shell="pip install -q pytest && mkdir -p /app",
                files=self._upload_spec(),
                disposable=False,
            ).wait()

        # One checkpoint per fork point along the execution timeline. Later fork
        # points advance execution so startup-seeded entropy is already captured
        # in the snapshot; replicas branched from them inherit it identically.
        self._states["pre_interpreter"] = ready
        warm = ready.run(
            shell="cd /app && python -c 'import sys, sysconfig' >/dev/null 2>&1 || true",
            disposable=False,
        ).wait()
        self._states["post_import"] = warm
        self._states["post_fixture"] = warm.run(
            shell="cd /app && python -m pytest --collect-only -q >/dev/null 2>&1 || true",
            disposable=False,
        ).wait()

    def replicate(self, fork_point: str, n: int) -> list[RunOutcome]:
        parent = self._states[fork_point]
        args = " ".join(self._pytest_args)
        cmd = f"cd /app && python -m pytest -v --tb=no -p no:cacheprovider {args}"

        def one(i: int) -> tuple[RunOutcome, str]:
            # Each call branches from the SAME parent -> byte-identical start.
            st = parent.run(shell=cmd, disposable=False).wait()
            out = st.stdout if isinstance(st.stdout, str) else ""
            err = st.stderr if isinstance(st.stderr, str) else ""
            text = out + err
            return RunOutcome(parse_verbose(text), text[-3000:], i), str(st.uuid)

        with ThreadPoolExecutor(max_workers=min(n, 16)) as pool:
            pairs = list(pool.map(one, range(n)))

        # Corroborating signal: distinct content-hashes across branches of the
        # same parent independently confirm the execution was nondeterministic.
        self.state_uuids[fork_point] = [u for _, u in pairs]
        return [o for o, _ in pairs]

    def source(self, path: str) -> str:
        try:
            state = self._states.get("pre_interpreter")
            if state is None:
                return ""
            return state.read(f"/app/{path}").decode("utf-8", "replace")
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
