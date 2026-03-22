# Meridian Proof Matrix

This file maps public claims to executable proof artifacts or live surfaces.

## Reference Proofs

| Claim | Proof Artifact | Notes |
| --- | --- | --- |
| Runtime-core and agent-runtime truth exists | `GET /api/context`, `GET /api/status`, `GET /api/agents`, `GET /api/runtimes`, `GET /api/admission`, `GET /api/federation` | Process-bound reference workspace, with agent `runtime_binding` surfaced and kept coherent with registry truth |
| Signed host-service federation exists | [`kernel/tests/test_federation.py`](../kernel/tests/test_federation.py) | Covers peer registry, replay protection, wrong-target rejection, settlement notice, case/court notice, witness archive |
| 3-host federation story exists | [`kernel/tests/test_three_host_federation_proof.py`](../kernel/tests/test_three_host_federation_proof.py) | Alpha/Beta/Gamma story with proposal, acceptance, execution review, court notice, breach notice, and witness archive |
| OpenClaw-compatible runtime seam exists | [`kernel/tests/test_openclaw_federation_proof.py`](../kernel/tests/test_openclaw_federation_proof.py) | Kernel-side reference adapter proof, not a live hosted OpenClaw deployment |
| Warrant-bound payouts exist | [`kernel/tests/test_treasury_capsule.py`](../kernel/tests/test_treasury_capsule.py) | Includes reserve-floor gate, phase gate, settlement adapter preflight, verifier-ready contract checks |
| Settlement notice fail-closed behavior exists | [`kernel/tests/test_workspace_context.py`](../kernel/tests/test_workspace_context.py) and [`kernel/tests/test_federation.py`](../kernel/tests/test_federation.py) | Invalid notices open cases and can suspend peers |

## Live Proofs

| Claim | Live Surface | Current Truth |
| --- | --- | --- |
| Live workspace exposes runtime-core and agent-runtime truth | `GET /api/context`, `GET /api/status`, `GET /api/agents`, `GET /api/runtimes` | Founding-only, single-org, honest boundary classification; bindings and runtime registry are surfaced consistently |
| Live treasury exposes settlement adapter contract | `GET /api/treasury/settlement-adapters` | `internal_ledger` ready; external adapters registered but not executable |
| Live preflight exposes settlement verifier blockers | `POST /api/treasury/settlement-adapters/preflight` | External adapters fail closed until verifier is ready and host support exists |
| Live service boundaries are explicitly classified | `GET /api/subscriptions`, `GET /api/accounting`, `GET /api/federation/manifest` | Canonical service module + compatibility role surfaced, no fake multi-host routing |
| Live readiness stays truthful | [`company/meridian_platform/readiness.py`](../../company/meridian_platform/readiness.py) | Founder-backed phase 0, treasury-blocked, customer revenue 0 |

## Public Proof Runner

Generate the high-signal public proof bundle:

```bash
python3 examples/generate_public_proof_bundle.py
```

To embed a truthful live host receipt as well, pass the public live manifest:

```bash
python3 examples/generate_public_proof_bundle.py \
  --live-manifest-url http://127.0.0.1:18901/api/federation/manifest
```

This emits a JSON artifact containing:

1. a three-host federation summary
2. an OpenClaw reference-adapter federation summary
3. an optional live host receipt from `GET /api/federation/manifest`
4. an explicit `not_live_proven` list

In restricted environments the bundle may mark a proof `skipped` instead of
failing, for example when localhost socket binding is unavailable. That is
expected and truthful.

The broader federation regression matrix remains in
[`kernel/tests/test_federation.py`](../kernel/tests/test_federation.py) and is
still part of the full test suite, but it is not part of the minimal public
proof runner because some localhost transport cases depend on the execution
environment allowing socket binding.

## Frontier, Not Yet Claimed As Live

- live multi-host federation between independent deployed Meridian hosts
- live OpenClaw end-to-end deployment wiring
- live MCP identity propagation beyond current founding-only boundaries
- non-`internal_ledger` settlement execution on a live host
