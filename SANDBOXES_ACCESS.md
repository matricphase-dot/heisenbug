# Requesting Nebius Sandboxes Beta access

Heisenbug's intended execution substrate is Nebius Token Factory **Sandboxes**. The code is
written and wired; the only blocker is a per-account Beta entitlement.

## Current state (verified)

```
project id : aiproject-e00ga87da6d3zwj57d      ← correct, accepted by the API
auth       : IAMAuth(token, project_id)        ← correct, sends the Project header
result     : 403 Insufficient permissions: list
```

Diagnosed with `python scripts/verify_setup.py`. The project ID is *accepted* — a wrong ID
returns a different error — so this is purely a missing Sandboxes role on the service account
behind the API key.

## Where to ask

1. **Nebius Discord** — https://discord.gg/ZdC3rXMJH (fastest; Nebius staff are active there)
2. **Email** — contree@nebius.com

## Message to send

> Subject: Sandboxes Beta access request — Global AI Hackathon (Coding & Agentic track)
>
> Hi,
>
> I'm building a project for the Nebius x NVIDIA Global AI Hackathon on the Coding and
> Agentic Engineering track, which is defined around agents that run and test code in Token
> Factory Sandboxes.
>
> My project (Heisenbug) classifies flaky tests by *cause* rather than frequency. It launches
> N replicas from one shared checkpoint — byte-identical execution state — and uses whether
> they diverge as proof of where the nondeterminism enters. ConTree's branching model is
> exactly the primitive this needs: `state.run()` returning a new branched state rather than
> mutating, so N calls on one parent give N identical starts.
>
> I'd like Sandboxes Beta access enabled so I can run against real Sandbox branches.
>
> Project ID: aiproject-e00ga87da6d3zwj57d
> Account: aadityamehra289@gmail.com
> Repo: https://github.com/matricphase-dot/heisenbug
>
> Two pieces of Beta feedback from integrating so far:
>
> 1. `ContreeSync(token=...)` silently selects `JWTAuth`, which omits the `Project` header
>    Sandboxes requires. The API then answers `400 Missing "Project" header`, and through the
>    SDK it surfaces as a bare `ForbiddenError` with nothing pointing at the real cause.
>    Sandboxes needs `IAMAuth(token=..., project_id=...)`. Making `token=` raise a clear error
>    for Sandboxes endpoints — or documenting `IAMAuth` in the quickstart — would save Beta
>    users real debugging time.
>
> 2. Entitlement is invisible until the first call. The Sandboxes panel appears in the console
>    sidebar and the SDK authenticates fine, then the first request 403s. Surfacing entitlement
>    state in the console would prevent building against an API you can't execute.
>
> Thanks,
> Aditya Mehra

## When access is granted

No code changes needed. Confirm with:

```bash
python scripts/verify_setup.py        # expect: ✓ Sandboxes reachable
python -m uvicorn backend.server:app --host 0.0.0.0 --port 8000
```

The UI's executor line will read **`nebius-sandboxes`** instead of `local-fork`, and each
replica becomes a real ConTree branch. Re-record video segment 4 at that point:

```bash
python video/record.py 04_live_run && python video/assemble.py
```
