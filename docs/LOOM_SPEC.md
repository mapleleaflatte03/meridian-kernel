# Meridian Loom — Runtime Specification

**Status:** PLANNED (0/7 contract compliance)
**Core language:** Rust (supervisor / runtime core)
**Worker languages:** Python, TypeScript (where appropriate)
**Sandbox:** WASM for capability modules
**Registry ID:** `meridian_loom`

Meridian Loom is the planned Meridian-native execution runtime. It is designed to
implement all 7 governance contract hooks natively — without adapter translation —
and to replace OpenClaw through a phased shadow-mode migration.

Loom is polyglot by design: a Rust supervisor manages lifecycle, isolation, and
governance bridging, while workers may be written in Python or TypeScript. WASM
sandboxing is used for capability modules where isolation matters.

This document began as a pure spec. An experimental public scaffold now exists
to validate the CLI shape, setup flow, local state layout, and rehearsal path.
That scaffold now includes experimental preflight surfaces for all seven
contract surfaces. Two remain preview-only surfaces today:
- `audit_emission` uses the kernel audit serializer to write a local preview
  file, not the kernel's canonical audit log
- `sanction_controls`, `approval_hook`, and `budget_gate` now read the
  kernel reference adapter through a read-only preflight path, but still do not
  provide native Loom enforcement or governed execution
- `loom shadow decide` now writes a standalone decision artifact using the same
  reference gate result, but that is still an experimental preflight surface,
  not governed runtime enforcement
- `loom shadow enforce` now returns fail-closed exit codes from that same
  decision surface, but it is still an experimental operator aid, not runtime
  enforcement

It still does **not** provide governed execution or any proven contract hooks.

---

## 1. Separation of Concerns

**Meridian Kernel** owns governance:
- Institution, Agent, Authority, Treasury, Court
- 7 contract hooks (identity, envelope, cost, approval, audit, sanctions, budget)

**Meridian Loom** owns execution:
- Process lifecycle (start, stop, health, restart)
- LLM call routing and model selection
- Tool execution and sandboxing
- Channel/transport adapters (Telegram, MCP, A2A, HTTP)
- Session management and context windows
- Container/WASM isolation
- Cron/scheduling primitives

**The boundary:** Loom calls UP into the Kernel via the 7 hooks.
The Kernel never calls down into Loom.

---

## 2. Contract Requirements

Every runtime in the Meridian ecosystem must satisfy 7 contract hooks
(defined in `kernel/runtimes.json` under `contract_requirements`).

| # | Hook | What Loom Must Do |
|---|------|-------------------|
| 1 | `agent_identity` | Provide stable unique agent ID mapping to kernel agent records |
| 2 | `action_envelope` | Wrap each governed action: agent_id, action_type, resource, estimated_cost_usd |
| 3 | `cost_attribution` | Report actual cost post-action via kernel `metering.record()` |
| 4 | `approval_hook` | Call `check_authority(agent_id, action)` before privileged actions; block on `False` |
| 5 | `audit_emission` | Emit structured events to kernel audit_log (timestamp, agent_id, action, outcome) |
| 6 | `sanction_controls` | Query `get_restrictions(agent_id)` per session; enforce restrictions |
| 7 | `budget_gate` | Call `check_budget(agent_id, cost)` before cost-bearing ops; block on `False` |

Current compliance: **0/7** (all `null` — unproven).

---

## 3. Target Performance

These are **directional goals**, not proven Meridian numbers. The current Loom
scaffold is non-functional as a runtime and provides no performance evidence.
Competitor observations are labeled with confidence based on source quality and
recency.

| Metric | Directional Target | Rationale | Confidence |
|--------|--------------------|-----------|------------|
| Memory | <50 MB | Comparable Rust runtimes (ZeroClaw, SkyClaw) report <15 MB in their docs; OpenClaw's JS runtime is observed at ~100 MB in local testing. Loom targets well below OpenClaw but does not claim parity with minimal embedded runtimes. | DIRECTIONAL — no Loom measurement exists |
| Cold start | <500 ms | ZeroClaw docs claim 10ms; OpenClaw observed at ~30s locally. Loom's target is conservative relative to reported Rust runtimes but aspirational relative to current state (no code). | DIRECTIONAL — no Loom measurement exists |
| Isolation | WASM + container | OpenFang demonstrates dual-metered WASM isolation. Loom plans the same architecture class. | DESIGN GOAL |
| Contract compliance | 7/7 native | The kernel defines 7 hooks. Loom aims to implement all natively without adapter translation. | DESIGN GOAL — current compliance: 0/7 |

**What these numbers are not:**
- Not proven Meridian benchmarks (no Loom binary exists)
- Not guaranteed post-implementation figures
- Not claims about competitor runtimes beyond what their public docs state

Actual Loom performance numbers will be published when Phase 1 (shadow mode)
produces measurable runtime data.

---

## 4. Module Layout

```
meridian-loom/
  loom.toml                       # Runtime config
  Cargo.toml                      # Rust supervisor manifest

  # ── Rust core (supervisor, lifecycle, governance bridge) ──
  src/
    main.rs                       # Entry point
    runtime/
      mod.rs
      lifecycle.rs                # Start, stop, health, restart
      session.rs                  # Session management
      scheduler.rs                # Cron + night-shift scheduling
    execution/
      mod.rs
      sandbox.rs                  # Container/WASM isolation boundary
      worker_spawn.rs             # Spawn Python/TS/Rust workers
      llm_router.rs               # Model selection + call routing
    transport/
      mod.rs
      telegram.rs                 # Telegram channel adapter
      mcp.rs                      # MCP server/client
      a2a.rs                      # A2A protocol adapter
      http.rs                     # HTTP API surface
    governance/
      mod.rs
      contract_bridge.rs          # 7-hook bridge to Meridian Kernel
      envelope.rs                 # Action envelope construction
      metering_emitter.rs         # Cost attribution emission

  # ── Workers (polyglot — language chosen per task) ──
  workers/
    python/                       # Python workers (research, analysis)
    typescript/                   # TypeScript workers (channel adapters)
    wasm/                         # WASM capability modules (sandboxed tools)

  tests/
    contract_compliance_test.rs   # Proves 7/7 compliance
    shadow_mode_test.rs           # Shadow vs. primary comparison
```

The Rust core handles lifecycle, isolation, and governance bridging. Workers are
spawned as separate processes (Python, TypeScript) or loaded as WASM modules.
The supervisor never assumes all execution logic is Rust.

---

## 5. Phased Migration

### Phase 0 — Spec + Scaffold (current)
- This document
- Registry entry with 0/7 compliance, status `"planned"`
- Experimental public scaffold for CLI/setup rehearsal plus 7-surface preflight coverage
- Experimental decision artifact (`loom shadow decide`) for operator review of the
  current gate outcome
- Experimental fail-closed command (`loom shadow enforce`) for shell automation
- Read-only reference-adapter gate evaluation for sanction/approval/budget surfaces
- No governed execution runtime

### Phase 1 — Shadow Mode
- Loom runs alongside OpenClaw, receiving same inputs, outputs discarded
- Governance hooks call the real kernel
- Target: 2/7 compliance (agent_identity + action_envelope)
- Verification: zero governance-check divergence over 3+ night-shift runs

### Phase 2 — Governed Worker Cells
- Loom executes real agent tasks in isolated cells
- Cost attribution and budget gate implemented
- Target: 5+/7 compliance
- Verification: single governed agent completes end-to-end in Loom

### Phase 3 — Capability ABI
- Stable binary interface for capabilities (tools, transports, sandboxes)
- Loadable without recompilation
- Target: 7/7 compliance maintained

### Phase 4 — Checkpoint/Sanction Native Layer
- Native checkpoint emission and sanction enforcement
- No adapter translation for restrictions
- Target: 7/7 compliance, sanctioned agent blocked natively

### Phase 5 — Native Ingress
- Telegram bot adapter, MCP server, scheduler
- Full OpenClaw replacement
- Justification gate: Phase 4 stable AND owner confirms retirement
- Verification: 7 consecutive clean night-shift runs before OpenClaw retirement

---

## 6. Verification

At each phase, the runtime adapter tooling assesses registry-declared
compliance. The tooling reads the `contract_compliance` fields in
`runtimes.json` and reports their current state — it does not independently
verify a live runtime:

```bash
# Show registry-declared state
python3 kernel/runtime_adapter.py show --runtime_id meridian_loom

# Report contract compliance from registry
python3 kernel/runtime_adapter.py check-contract --runtime_id meridian_loom
```

`null` = unproven (no test exists), `true` = proven by a passing test,
`false` = tested and non-compliant.
No field is set to `true` until a test proves it. The registry is the
source of truth; the tooling reports what it says.
