# Meridian Constitutional Kernel

Open-source kernel for governed digital labor built on five primitives:
**Institution, Agent, Authority, Treasury, and Court.**

```
pip install: not required — pure Python stdlib
quickstart:  python3 quickstart.py
demo:        http://localhost:18901 (governed workspace)
```

---

## What This Is

Meridian is a constitutional operating system for AI agents. It provides the
governance layer that sits between "agents that can do things" and
"agents that should be trusted to do things."

If you run AI agents that spend money, make decisions, or produce work product,
you need governance primitives — not just prompts.

Meridian gives you five:

| Primitive | What It Does |
|-----------|-------------|
| **Institution** | Charter-governed container with lifecycle management and policy defaults |
| **Agent** | First-class identity with scopes, budget, risk state, and lifecycle |
| **Authority** | Approval queues, delegations, kill switch, sprint leadership |
| **Treasury** | Real money tracking with balance, runway, reserve floor, and budget enforcement |
| **Court** | Violations, sanctions, appeals, remediation — severity-based enforcement |

These compose over a three-ledger economy: **REP** (reputation/trust),
**AUTH** (temporary authority), and **CASH** (real money). Agents earn
reputation through accepted work, gain temporary authority from recent
output, and spend real budget under treasury constraints.

## Why Now

AI agents are getting deployed into production. Most governance is
either "trust the prompt" or "build a custom permissions system per tool."

Neither scales. What scales is a small, composable kernel that any
agent runtime can adopt — the way Unix permissions work regardless of
which shell you use.

## What Is Open

Everything in this repo. The five kernel primitives, the economy layer
they compose over, the governed workspace demo, and a complete example
vertical. Apache-2.0 licensed.

## What Is Not Open

The hosted Meridian service (delivery pipelines, payment processing,
customer data, proprietary research sources). See
[OPEN_SOURCE_BOUNDARY.md](OPEN_SOURCE_BOUNDARY.md) for the full list.

You don't need the hosted service. This kernel runs standalone.

---

## Quickstart (Under 10 Minutes)

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

### Try It

```bash
# Check system status
python3 kernel/workspace.py --port 18901 &

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

## Architecture at a Glance

```
┌─────────────────────────────────────────────┐
│  Governed Workspace (workspace.py)          │
│  Owner-facing dashboard + JSON API          │
├─────────────────────────────────────────────┤
│  Kernel Primitives                          │
│  ┌───────────┐ ┌───────┐ ┌───────────┐     │
│  │Institution│ │ Agent │ │ Authority │     │
│  └───────────┘ └───────┘ └───────────┘     │
│  ┌───────────┐ ┌───────┐                   │
│  │ Treasury  │ │ Court │                   │
│  └───────────┘ └───────┘                   │
├─────────────────────────────────────────────┤
│  Economy Layer                              │
│  REP (reputation) + AUTH (authority)        │
│  + CASH (treasury) + Sanctions + Scoring    │
├─────────────────────────────────────────────┤
│  Your Agent Runtime                         │
│  (OpenClaw, LangChain, CrewAI, custom, ...) │
└─────────────────────────────────────────────┘
```

The kernel doesn't run your agents. It governs them. Plug it into
whatever agent runtime you use.

### Composition Pattern

Kernel primitives compose over the economy layer — they import and extend,
never rewrite:

| Economy Module | Kernel Primitive | What's Composed |
|---------------|-----------------|-----------------|
| `economy/authority.py` | `kernel/authority.py` | Sprint leadership, action rights, block matrix |
| `economy/sanctions.py` | `kernel/court.py` | Sanction application, lifting, restriction checks |
| `economy/score.py` | `kernel/agent_registry.py` | REP/AUTH scoring synced to agent risk state |
| `economy/revenue.py` | `kernel/treasury.py` | Balance, runway, budget enforcement |

### State Files

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

The `examples/intelligence/` directory shows a complete agent workflow
mapped onto the five primitives:

```
Research (Atlas) → Write (Quill) → QA (Sentinel) → Accept (Aegis)
    → Execute (Forge) → Compress (Pulse) → Deliver → Score
```

Each phase checks authority, respects budget gates, and records court
violations on failure. The preflight command checks all constitutional
gates before the pipeline runs.

This is an example workload, not the definition of Meridian. You can
build any governed workflow on the same kernel.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). No CLA required — Apache-2.0
inbound = outbound.

Good places to start:
- Issues labeled `good first issue`
- Issues labeled `help wanted`
- Adding a new example vertical
- Improving the governed workspace UI
- Writing tests for kernel primitives

## Security

Report vulnerabilities privately per [SECURITY.md](SECURITY.md).
Do not open public issues for security bugs.

## Sponsorship

If Meridian is useful to your work, consider
[sponsoring the project](https://github.com/sponsors/mapleleaflatte03).

Sponsors help fund:
- Kernel development and maintenance
- Security audits
- Documentation and examples
- Community infrastructure

## License

Apache-2.0. See [LICENSE](LICENSE).

## Links

- [Architecture](ARCHITECTURE.md)
- [Open-Source Boundary](OPEN_SOURCE_BOUNDARY.md)
- [Economy Constitution](economy/ECONOMY_CONSTITUTION.md)
- [Roadmap](ROADMAP.md)
- [Governance](GOVERNANCE.md)
