# Meridian Constitutional Kernel

**Five primitives for governing digital labor: Institution · Agent · Authority · Treasury · Court.**

Pure Python. No external dependencies. Apache-2.0.

---

**Meridian does not run your agents. It governs them.**

Any runtime — MCP-backed apps, LangChain pipelines, OpenClaw, A2A agents, or your own stack — can have its agents governed by the same five primitives. The governance layer is independent of the execution layer.

| Primitive | What It Does |
|-----------|-------------|
| **Institution** | Charter-governed container with lifecycle management and policy defaults |
| **Agent** | First-class identity with scopes, budget, risk state, and lifecycle |
| **Authority** | Approval queues, delegations, kill switch, sprint leadership |
| **Treasury** | Real money tracking: balance, runway, reserve floor, and budget enforcement |
| **Court** | Violations, sanctions, appeals, remediation — severity-based enforcement |

These compose over a three-ledger economy: **REP** (reputation/trust), **AUTH** (temporary authority), and **CASH** (real money). Agents earn reputation through accepted work, gain temporary authority from recent output, and spend real budget under treasury constraints.

---

## The Governance Gap

Runtimes are proliferating. MCP is a major open standard for tool connectivity. A2A is pushing agent-to-agent interoperability across vendors. Enterprise platforms are adding agent identity. Payment rails are adding agentic commerce.

In this world, the execution layer fragments — every team, vendor, and platform will have a runtime. What doesn't fragment is the need for governance: identity, authority, budget, accountability, and dispute resolution.

**Meridian is the governance layer above the runtime layer** — the same way Unix permissions work regardless of which shell or application you use.

If you run AI agents that spend money, make decisions, or produce work product, you need governance primitives. Not just prompts.

---

## What Is Open

Everything in this repo: the five kernel primitives, the economy layer they compose over, the governed workspace demo, and a complete example vertical. Apache-2.0 licensed.

## What Is Not Open

The hosted Meridian service — delivery pipelines, payment processing, customer data, proprietary research sources. See [OPEN_SOURCE_BOUNDARY.md](OPEN_SOURCE_BOUNDARY.md) for the full list.

You don't need the hosted service. This kernel runs standalone.

---

## Who This Is For

**Use Meridian if you:**
- Run AI agents that spend money, call APIs, or produce work product
- Need governance beyond "trust the prompt" but don't want to build it from scratch
- Want agents to have identity, budgets, authority, and accountability
- Need a kill switch, approval queues, or sanction enforcement
- Want to separate governance from your agent runtime — and keep that separation as runtimes evolve (MCP, A2A, custom)
- Want to govern agents across multiple runtimes with a single kernel

**This is not for you if you** need a chatbot framework, an agent runner, or a mature ecosystem with hundreds of integrations. Meridian is the governance layer — it doesn't run your agents, it governs them.

---

## Quickstart

**Requirements:** Python 3.9+, no external dependencies.

```bash
git clone https://github.com/mapleleaflatte03/meridian-kernel.git
cd meridian-kernel
python3 quickstart.py
```

This will:
1. Initialize an example institution with charter and policies
2. Register seven example agents with roles, budgets, and scopes
3. Set up the economy (reputation, authority, treasury)
4. Start the governed workspace at `http://localhost:18901`

Open the dashboard to see all five primitives live:
- View agent reputation and authority scores
- Engage/disengage the kill switch
- File and resolve court violations
- Check treasury runway and budget gates
- Run the example intelligence vertical preflight

### Try the primitives directly

```bash
# Run the example vertical preflight
python3 examples/intelligence/ci_vertical.py preflight

# File a test violation
python3 kernel/court.py file \
  --agent atlas --org meridian \
  --type weak_output --severity 2 \
  --evidence "Test violation for demo"

# Check the court record
python3 kernel/court.py show

# Check treasury budget gate
python3 kernel/treasury.py check-budget --agent_id atlas --cost 0.50

# Engage the kill switch
python3 kernel/authority.py kill-switch on --by owner --reason "Testing"
python3 kernel/authority.py show
python3 kernel/authority.py kill-switch off --by owner
```

---

## Architecture

```
┌───────────────────────────────────────────────────────┐
│  Governed Workspace (workspace.py)                    │
│  Owner-facing dashboard + JSON API                    │
├───────────────────────────────────────────────────────┤
│  Kernel Primitives                                    │
│  ┌───────────┐ ┌───────┐ ┌───────────┐ ┌──────────┐ │
│  │Institution│ │ Agent │ │ Authority │ │ Treasury │ │
│  └───────────┘ └───────┘ └───────────┘ └──────────┘ │
│  ┌─────────┐ ┌────────────────────────────────────┐  │
│  │  Court  │ │ Runtime Adapter (runtime_adapter.py)│  │
│  └─────────┘ └────────────────────────────────────┘  │
├───────────────────────────────────────────────────────┤
│  Economy Layer                                        │
│  REP (reputation) + AUTH (authority)                  │
│  + CASH (treasury) + Sanctions + Scoring              │
├───────────────────────────────────────────────────────┤
│  Runtime Adapter Layer (runtime-neutral)              │
│  ┌─────────────┐ ┌──────────────┐ ┌───────────────┐  │
│  │ local_kernel│ │  openclaw_   │ │  mcp_generic  │  │
│  │  (built-in) │ │  compatible  │ │   (planned)   │  │
│  └─────────────┘ └──────────────┘ └───────────────┘  │
│  ┌─────────────┐ ┌──────────────┐                    │
│  │ a2a_generic │ │ your runtime │                    │
│  │  (planned)  │ │  (register)  │                    │
│  └─────────────┘ └──────────────┘                    │
└───────────────────────────────────────────────────────┘
```

The kernel doesn't run your agents. It governs them. Any runtime that satisfies the [Constitutional Runtime Contract](docs/RUNTIME_CONTRACT.md) can have its agents governed by the same five primitives.

## Runtime Adapters

Meridian is runtime-neutral. Five runtimes are currently registered:

| Runtime | Protocol | Contract Status |
|---------|----------|----------------|
| `local_kernel` | custom | Compliant (7/7) — built-in reference |
| `openclaw_compatible` | custom | Partial (5/7) — adapter work underway |
| `mcp_generic` | MCP | Non-compliant (2/7) — planned adapter in v0.2 |
| `a2a_generic` | A2A | Non-compliant (1/7) — planned adapter in v0.2 |
| `openfang_compatible` | custom | Unknown — planned |

```bash
# Check contract compliance for all runtimes
python3 kernel/runtime_adapter.py check-all

# Register your own runtime
python3 kernel/runtime_adapter.py register \
  --id my_runtime --label "My Runtime" \
  --type hosted --protocols "MCP,custom" --identity_mode api_key
```

The [Constitutional Runtime Contract](docs/RUNTIME_CONTRACT.md) defines the seven integration hooks and includes a minimal integration example.

## Composition Pattern

Kernel primitives compose over the economy layer — they import and extend, never rewrite:

| Economy Module | Kernel Primitive | What's Composed |
|---------------|-----------------|-----------------|
| `economy/authority.py` | `kernel/authority.py` | Sprint leadership, action rights, block matrix |
| `economy/sanctions.py` | `kernel/court.py` | Sanction application, lifting, restriction checks |
| `economy/score.py` | `kernel/agent_registry.py` | REP/AUTH scoring synced to agent risk state |
| `economy/revenue.py` | `kernel/treasury.py` | Balance, runway, budget enforcement |

## State Files

All state is JSON/JSONL on the local filesystem. No database required.

| File | Contents |
|------|----------|
| `kernel/organizations.json` | Institutions with charters and policies |
| `kernel/agent_registry.json` | Agents with scores, budgets, risk states |
| `kernel/authority_queue.json` | Pending approvals, delegations, kill switch |
| `kernel/court_records.json` | Violations, sanctions, appeals |
| `kernel/audit_log.jsonl` | Append-only audit trail |
| `kernel/metering.jsonl` | Usage metering events |
| `economy/ledger.json` | Economy state (REP, AUTH, CASH per agent) |

---

## Example Vertical: Competitive Intelligence

The `examples/intelligence/` directory shows a complete agent workflow mapped onto the five primitives:

```
Research (Atlas) → Write (Quill) → QA (Sentinel) → Accept (Aegis)
    → Execute (Forge) → Compress (Pulse) → Deliver → Score
```

Each phase checks authority, respects budget gates, and records court violations on failure. The preflight command checks all constitutional gates before the pipeline runs.

This is an example workload, not the definition of Meridian. You can build any governed workflow on the same kernel.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). No CLA required — Apache-2.0 inbound = outbound.

Good places to start:
- Issues labeled `good first issue`
- Issues labeled `help wanted`
- Adding a new example vertical
- Improving the governed workspace UI
- Writing tests for kernel primitives

## Security

Report vulnerabilities privately per [SECURITY.md](SECURITY.md). Do not open public issues for security bugs.

## Sponsorship

If Meridian is useful to your work, consider [sponsoring the project](https://github.com/sponsors/mapleleaflatte03). GitHub Sponsors is the primary funding path.

Sponsors help fund kernel development, security audits, documentation, and community infrastructure.

For crypto sponsorship (USDC on Base), see the wallet registry in [`treasury/wallets.json`](treasury/wallets.json). All contributions are governed by the [Contributor Treasury Protocol](docs/treasury/CONTRIBUTOR_TREASURY_PROTOCOL.md).

## License

Apache-2.0. See [LICENSE](LICENSE).

---

[Architecture](ARCHITECTURE.md) · [Open-Source Boundary](OPEN_SOURCE_BOUNDARY.md) · [Economy Constitution](economy/ECONOMY_CONSTITUTION.md) · [Roadmap](ROADMAP.md) · [Governance](GOVERNANCE.md)
