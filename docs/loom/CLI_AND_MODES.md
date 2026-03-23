# Meridian Loom — CLI and Operating Modes

**Status:** Design document (no implementation yet)

## CLI Surface

The Loom binary exposes a minimal CLI. Commands are deliberately few —
Loom is a runtime, not a Swiss Army knife.

### Core commands

```
loom init              Create loom.toml and initialize local state
loom start             Start the runtime (reads loom.toml)
loom stop              Graceful shutdown
loom health            Structured health check (JSON)
loom status            Human-readable status summary
loom config show       Print resolved configuration
loom config set <k> <v>  Set a config value in loom.toml
```

`loom init` accepts `--mode shadow|standalone|embedded` (default: `standalone`)
and `--kernel-path <path>` (required for standalone/shadow, ignored for embedded).
It writes a `loom.toml` in the current directory. If one already exists, it
exits with an error — no silent overwrite.

### Governance commands

```
loom contract check    Run 7-hook compliance check against kernel
loom contract show     Show current compliance state (null/true/false per hook)
```

### Worker commands

```
loom worker list       List registered workers and their status
loom worker spawn <id> Manually spawn a worker (debug/dev use)
loom worker stop <id>  Stop a specific worker
```

### Shadow mode commands (Phase 1)

```
loom shadow start      Start in shadow mode alongside primary runtime
loom shadow compare    Diff governance events: Loom vs primary
loom shadow report     Summary of shadow-mode divergence
```

### Scheduler commands (Phase 5)

```
loom schedule list     Show scheduled jobs
loom schedule run <id> Trigger a job immediately
```

## Operating Modes

Loom has three modes. The mode is set in `loom.toml` under `[runtime].mode`.

### 1. Shadow mode (`mode = "shadow"`)

**Purpose:** Run alongside the primary runtime (OpenClaw) without affecting
production. Loom receives the same inputs and runs the same governance hooks
but its outputs are discarded.

**When to use:** Phase 1 — proving that Loom's governance checks produce
identical results to the primary runtime.

**What it does:**
- Listens for the same cron/scheduling events as the primary runtime
- Calls the kernel's 7-hook API for each event
- Logs governance events tagged `"source": "loom_shadow"`
- Does NOT deliver outputs to any channel
- Produces a comparison report: `loom shadow compare`

**What it proves:** Governance-check parity without production risk.

### 2. Standalone mode (`mode = "standalone"`)

**Purpose:** Loom is the only runtime. It owns lifecycle, execution,
governance bridging, and transport.

**When to use:** Phase 5 — after Loom has proven 7/7 compliance and passed
the OpenClaw retirement gate.

**What it does:**
- Full lifecycle management (start, stop, health, restart)
- Worker spawning and isolation
- Transport adapters (Telegram, MCP, HTTP)
- Governance hooks called for every action
- Scheduler/cron execution

**Requirement:** The Meridian Kernel must be accessible — either as a local
path or (future) a remote API.

### 3. Embedded mode (`mode = "embedded"`)

**Purpose:** Loom bundles a compiled subset of the kernel's governance checks
so that a user can run Loom without separately installing or configuring the
full kernel.

**When to use:** When a user wants to try Loom with minimal setup. The
embedded kernel subset provides governance checks but does not include the
full kernel administration surface (institution management, court operations,
etc.).

**What it does:**
- Includes a vendored, compiled governance library derived from the kernel
- Provides the 7-hook contract interface without a separate kernel process
- Uses a local SQLite store for audit log, budget tracking, and agent state
- Does NOT provide the full kernel administration CLI or multi-institution
  routing

**Trade-offs:**

| Aspect | Embedded | Standalone (with separate kernel) |
|--------|----------|-----------------------------------|
| Setup complexity | Lower — single binary | Higher — two components |
| Governance surface | 7 hooks only | Full kernel (court, institution mgmt, etc.) |
| Multi-institution | No | Yes (kernel supports it) |
| Audit trail | Local SQLite | Kernel's canonical audit log |
| Upgrades | Coupled to Loom releases | Independent kernel/Loom upgrades |

**When embedded mode is NOT enough:**
- You need multi-institution governance
- You need the court/sanctions administrative surface
- You need the kernel's canonical audit log format for compliance
- You want to run multiple runtimes against one kernel

In those cases, use standalone mode with a separately installed kernel.

## How "user only needs Loom" works

For a user who wants to evaluate Loom without understanding the full Meridian
ecosystem:

```bash
# 1. Install Loom
cargo install meridian-loom   # or build from source

# 2. Initialize with embedded governance
loom init --mode embedded

# 3. Start
loom start

# 4. Check health
loom health
```

This creates a `loom.toml` with `mode = "embedded"`, initializes the local
governance store, and starts the runtime. The user gets:
- Agent identity management (register, list, inspect)
- Budget tracking per agent
- Audit logging to local store
- Worker spawning with governance checks

They do NOT get multi-institution support, court/sanctions administration,
or the broader kernel ecosystem. Those require upgrading to standalone mode
with a full kernel install.

## CLI design principles

1. **No implicit behavior.** Every action requires an explicit command or
   config entry. Loom does not auto-discover or auto-configure.
2. **Structured output.** `loom health` and `loom contract check` return JSON.
   `loom status` returns human-readable text. Both formats are always available
   via `--json` / `--human` flags.
3. **No destructive defaults.** `loom start` in a directory without `loom.toml`
   fails with an error, not a wizard.
4. **Config is the truth.** The CLI modifies `loom.toml`; `loom.toml` drives
   behavior. There is no hidden state beyond what the config file declares.
