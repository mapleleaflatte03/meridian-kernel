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
- **Revenue summary** — read facade over economy layer
- **Contributor protocol** — wallet registry, payout proposals, funding sources

No new state file — treasury reads from `economy/ledger.json` and
`kernel/metering.jsonl`.

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
- **Contract checker** — verifies each runtime against the seven constitutional
  requirements
- **Registration** — new runtimes register themselves with contract compliance data
- **CLI** — `runtime_adapter.py list`, `check-contract`, `check-all`

Currently registered runtimes:

| Runtime | Type | Contract Status |
|---------|------|----------------|
| `local_kernel` | local | Compliant (7/7) |
| `openclaw_compatible` | hosted | Partial (5/7) |
| `mcp_generic` | mcp_app | Non-compliant (2/7, planned adapter) |
| `a2a_generic` | a2a_agent | Non-compliant (1/7, planned adapter) |
| `openfang_compatible` | hosted | Unknown (0/7, planned) |

See [Constitutional Runtime Contract](docs/RUNTIME_CONTRACT.md) for the full
requirements and integration guide.

## Economy Layer

The kernel composes over a three-ledger economy:

| Ledger | Purpose | Properties |
|--------|---------|------------|
| **REP** (reputation) | Long-term trust | Non-transferable, earned from accepted output, decays on inactivity |
| **AUTH** (authority) | Temporary power | Earned from recent output, decays every epoch, suspendable |
| **CASH** (treasury) | Real money | Only from owner capital or customer payments, never self-minted |

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
- Future storage backends (SQLite, PostgreSQL) planned for v0.4

State files are gitignored by default. The `bootstrap.py` script
initializes clean state for a new deployment.

## Governed Workspace

`kernel/workspace.py` serves an HTML dashboard + JSON API on a local port.
This is the owner-facing control surface:

- **GET endpoints** — read all primitive state including runtime registry
- **POST endpoints** — engage kill switch, file violations, approve requests, etc.
- **Auto-refresh** — dashboard updates every 15 seconds
- **Audit trail** — every action logged

The workspace is a demo/reference surface, not a production UI.
Production deployments would build their own control plane on top of the
JSON API. External runtimes can call the JSON API directly for governance
checks instead of importing Python modules.

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
primitive:
- Wallet registry with five verification levels
- Three treasury sub-accounts (company, maintainer, contributor)
- Payout proposal state machine with 72-hour dispute window
- Fraud and dispute policy mapping to the Court primitive

See [Contributor Treasury Protocol](docs/treasury/CONTRIBUTOR_TREASURY_PROTOCOL.md).
