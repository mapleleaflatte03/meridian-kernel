# Architecture

## Design Thesis

AI agents need governance the same way processes need an operating system.
Meridian provides five composable primitives that any agent runtime can adopt
to enforce identity, authority, budget, and accountability.

**Meridian does not run agents. It governs them.**

Any runtime — local subprocess, hosted API, MCP-backed tool server, A2A-capable
agent, LangGraph pipeline, or custom stack — can have its agents governed by
Meridian if it satisfies the [Constitutional Runtime Contract](docs/RUNTIME_CONTRACT.md).

## Runtime-Neutral Design

Meridian is the governance layer, not the execution layer. This is a deliberate
architectural choice:

| Layer | What It Does | Who Owns It |
|-------|-------------|-------------|
| **Agent Runtime** | Executes agents, manages LLM calls, routes tools | You |
| **Meridian Kernel** | Governs agents: identity, authority, budget, accountability | Meridian |
| **Economy Layer** | Scoring, sanctions, authority mechanics | Meridian |

This separation means:
- You keep your runtime architecture
- Meridian handles constitutional enforcement at the boundary
- Switching runtimes does not require rebuilding governance
- Multiple runtimes can share the same Meridian kernel

The [Constitutional Runtime Contract](docs/RUNTIME_CONTRACT.md) defines the
seven integration hooks that make a runtime governable.

## Current Proof Boundary

Meridian is runtime-neutral in design, but the current public proof is still
deliberately narrow:

- the five kernel primitives are real
- the reference workspace is real
- `runtime_core` now surfaces institution context, host identity, boundary
  identity model, service registry, admission state, and federation gateway
  state as machine-readable state
- one built-in runtime path (`local_kernel`) is the real reference adapter
- one external runtime family (`openclaw_compatible`) now has a tested
  kernel-side reference adapter library
- one host-service federation primitive now exists as a kernel reference:
  HMAC-signed envelopes, peer registry, and replay protection

What is not yet broadly proven in public code:
- live end-to-end OpenClaw-compatible deployment wiring
- general MCP middleware enforcement
- general A2A adapter enforcement
- live multi-institution routing inside one deployed service boundary

That means the thesis is larger than the current adapter proof, by design.
The code now says that honestly instead of implying otherwise.

## System Diagram

```
┌────────────────────────────────────────────────────────┐
│  Governed Workspace (workspace.py)                     │
│  Owner-facing dashboard + JSON API                     │
├────────────────────────────────────────────────────────┤
│  Kernel Primitives                                     │
│  ┌───────────┐ ┌───────┐ ┌───────────┐ ┌──────────┐  │
│  │Institution│ │ Agent │ │ Authority │ │ Treasury │  │
│  └───────────┘ └───────┘ └───────────┘ └──────────┘  │
│  ┌─────────┐ ┌──────────────────┐                     │
│  │  Court  │ │ Runtime Adapter  │                     │
│  └─────────┘ └──────────────────┘                     │
├────────────────────────────────────────────────────────┤
│  Economy Layer                                         │
│  REP (reputation) + AUTH (authority)                   │
│  + CASH (treasury) + Sanctions + Scoring               │
├────────────────────────────────────────────────────────┤
│  Runtime Adapter Layer                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │ Local Kernel │  │  OpenClaw-   │  │ MCP Generic │ │
│  │ (built-in)   │  │  compatible  │  │  (planned)  │ │
│  └──────────────┘  └──────────────┘  └─────────────┘ │
│  ┌──────────────┐  ┌──────────────┐                   │
│  │ A2A Generic  │  │   Custom /   │                   │
│  │  (planned)   │  │   Your Own   │                   │
│  └──────────────┘  └──────────────┘                   │
└────────────────────────────────────────────────────────┘
```

## Five Primitives

### Institution (`kernel/organizations.py`)

The top-level governed container. Every agent, budget, and policy exists
within an institution.

- **Charter** — founding purpose and constitutional text
- **Policy defaults** — budget caps, approval thresholds, sanction rules
- **Lifecycle** — `founding` → `active` → `suspended` → `dissolved`
- **Settings** — extensible key-value configuration

### Agent (`kernel/agent_registry.py`)

First-class managed entity with identity and governance state.

- **Identity** — unique ID, name, role, purpose, organization membership
- **Scopes** — what the agent is allowed to do (e.g., `read`, `research`, `execute`)
- **Budget** — per-run and per-day spending limits
- **Risk state** — `nominal` → `elevated` → `critical` → `suspended`
- **Lifecycle** — `provisioned` → `active` → `quarantined` → `decommissioned`
- **Economy participation** — REP score, AUTH score, incident count
- **Runtime binding** — optional field mapping agent to a specific runtime ID

Risk auto-escalation: 3+ incidents → elevated, 5+ → critical.

### Authority (`kernel/authority.py`)

Controls who can do what and when.

- **Approval queue** — agents request permission for actions; approvers decide
- **Delegations** — time-boxed scope delegation between agents
- **Kill switch** — global halt on all non-owner actions across all runtimes
- **Sprint leadership** — rotating lead rights based on authority score
- **Action checks** — composable `check_authority(agent, action)` gate

Composes over `economy/authority.py` which provides the scoring and block matrix.

### Treasury (`kernel/treasury.py`)

Real money tracking with enforcement.

- **Balance** — actual cash held
- **Reserve floor** — minimum balance policy
- **Runway** — balance minus reserve floor (negative = blocked)
- **Budget enforcement** — `check_budget(agent, cost)` blocks when underfunded
- **Spend tracking** — per-agent, per-org metering (runtime-reported)
- **Revenue summary** — governance facade over the economy layer
- **Contributor protocol** — wallet registry, payout proposals, funding sources

No new database layer — treasury resolves through capsule-backed economy state
and `kernel/metering.jsonl`.

### Court (`kernel/court.py`)

Accountability enforcement.

- **Violations** — typed records (weak output, rejected output, rework,
  token waste, false confidence, critical failure)
- **Severity ladder** — 1-6, mapping to escalating sanctions
- **Sanctions** — probation, lead ban, zero authority, remediation only
- **Appeals** — agents can challenge violations; decisions lift or uphold sanctions
- **Remediation** — structured path back from sanctions after violations resolve
- **Auto-review** — wraps economy sanctions into court violation records

Severity-to-sanction mapping:

| Severity | Type | Sanction |
|----------|------|----------|
| 1-2 | Light failure | None (no reward) |
| 3 | Rejected output | Probation |
| 4 | Rework creation | Lead ban |
| 5 | False confidence | Zero authority |
| 6 | Critical failure | Remediation only |

## Runtime Adapter Primitive (`kernel/runtime_adapter.py`)

The runtime adapter is the bridge between Meridian governance and external
agent runtimes. It provides:

- **Runtime registry** (`kernel/runtimes.json`) — machine-readable catalog of
  registered runtimes with protocol support, identity mode, and contract status
- **Contract checker** — reports registry-declared compliance against the seven
  constitutional requirements
- **Registration** — new runtimes register themselves with contract compliance data
- **CLI** — `runtime_adapter.py list`, `check-contract`, `check-all`

Currently registered runtimes:

| Runtime | Type | Contract Status |
|---------|------|----------------|
| `local_kernel` | local | Compliant (7/7) |
| `openclaw_compatible` | hosted | Reference adapter (7/7 via tested kernel-side library) |
| `mcp_generic` | mcp_app | Planned (2/7, no adapter yet) |
| `a2a_generic` | a2a_agent | Planned (1/7, no adapter yet) |
| `openfang_compatible` | hosted | Planned (0/7, no adapter yet) |

See [Constitutional Runtime Contract](docs/RUNTIME_CONTRACT.md) for the full
requirements and integration guide. Today the built-in `local_kernel` path is
the real reference runtime path, and `openclaw_compatible` now has a tested
kernel-side reference adapter library. That is real public adapter proof, but
it is still not the same thing as a live deployment proving runtime-side event
routing end-to-end.

## Economy Layer

The kernel composes over a three-ledger economy:

| Ledger | Purpose | Properties |
|--------|---------|------------|
| **REP** (reputation) | Long-term trust | Non-transferable, earned from accepted output, decays on inactivity |
| **AUTH** (authority) | Temporary power | Earned from recent output, decays every epoch, suspendable |
| **CASH** (treasury) | Real money | Only from owner capital, support contributions, or customer payments, never self-minted |

Key rule: these ledgers are **never collapsed into one token**. REP measures
trust, AUTH measures current authority, CASH measures money. Agents optimize
for value creation, not token accumulation.

## Composition Pattern

```
┌──────────────────────────────┐
│  Kernel Primitives           │  Composes over economy layer
│  (governance, enforcement)   │  Imports and extends, never rewrites
├──────────────────────────────┤
│  Economy Layer               │  Scoring, sanctions, authority rules
│  (REP, AUTH, CASH mechanics) │  The computational substrate
├──────────────────────────────┤
│  Agent Runtime               │  Any execution environment
│  (your choice)               │  MCP, A2A, LangChain, OpenClaw, custom
└──────────────────────────────┘
```

Each kernel primitive imports specific functions from economy modules
using `importlib.util.spec_from_file_location()` to avoid name collisions
(both layers have files named `authority.py`).

## State Management

All state is JSON/JSONL on the local filesystem. This is deliberate:
- No database dependency for getting started
- Easy to inspect, backup, and version
- Append-only audit trail via JSONL
- Alternative storage backends (SQLite, PostgreSQL) are possible future extensions

State files are gitignored by default. The `bootstrap.py` script
initializes clean state for a new deployment.

## Governed Workspace

`kernel/workspace.py` serves an HTML dashboard + JSON API on a local port.
This is the owner-facing control surface:

- **GET endpoints** — read all primitive state including runtime registry
- **POST endpoints** — engage kill switch, file violations, approve requests, etc.
- **Auto-refresh** — dashboard updates every 15 seconds
- **Audit trail** — every action logged

The workspace is a single-institution demo/reference surface, not a production UI.
It binds the process to exactly one institution, either by default founding/demo
selection or explicitly via `--org-id`. `/api/context` reports that bound
context, and request-level `org_id` or `X-Meridian-Org-Id` hints are only
accepted on exact match. There is still no request-level multi-org routing or
org-scoped auth. The optional workspace auth scope can also be pinned with
`MERIDIAN_WORKSPACE_AUTH_ORG_ID` or `org_id:` in the credentials file so
Basic-auth credentials and bound institution agree explicitly. Add
`MERIDIAN_WORKSPACE_USER_ID` or `user_id:` as well if you want mutation
authorization and audit attribution to resolve through a real institution
member role instead of a generic Basic-auth username. `/api/context` now
returns the effective mutation permission snapshot for that bound actor.
`/api/context` and `/api/status` also expose `runtime_core`, which answers
three runtime-core questions directly in surfaced state:
- what institution this process is acting for
- what host is serving that institution
- what identity model governs the current boundary
- how additional institutions are admitted without cross-org bleed
- whether host-service federation is enabled and which peers are trusted

In the OSS reference workspace, the current admission mode is
`single_process_per_institution`: a second institution is admitted by binding a
separate process, not by turning on request-level multi-org routing.
The federation gateway is now a real boundary in the service registry, but it
remains a host-service primitive. It proves signed cross-host identity and
replay protection, not broad multi-host execution parity.
Production deployments would build their own control plane
or adapter bridge on top of the Python primitives.  The demo JSON API is a
reference surface, not a full remote governance adapter API.

For the concrete handoff from local demo to real deployment, see
[Deployment Guide](docs/DEPLOYMENT_GUIDE.md).

## Example Vertical

`examples/intelligence/` demonstrates how to map a real workflow onto the
five primitives. It is one example vertical — not the definition of Meridian.

Any workflow can be mapped the same way:
- Phase-to-agent mapping
- Preflight gates checking all five primitives before execution
- Post-mortem analysis that files court violations on failures
- Budget enforcement per phase
- Authority checks per action

The intelligence vertical uses the `local_kernel` runtime. The same
constitutional pipeline applies to any runtime that satisfies the contract.

## Subsystems

### Contributor Treasury Protocol

`treasury/` contains the contributor economy layer built on top of the Treasury
primitive.  The protocol registries (wallets, accounts, contributors, maintainers,
payout proposals, funding sources) define the schema and state machines but have
**zero real entries** — no payouts have ever been executed.  This is infrastructure
ready for use when the project has real contributors and revenue.

- Wallet registry with five verification levels
- Payout proposal state machine with 72-hour dispute window
- Fraud and dispute policy mapping to the Court primitive

See [Contributor Treasury Protocol](docs/treasury/CONTRIBUTOR_TREASURY_PROTOCOL.md).
