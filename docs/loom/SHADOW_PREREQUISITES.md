# Loom Shadow Mode Prerequisites

## Purpose

This document lists the prerequisites for Loom Phase 1 (shadow mode).
It is a checklist, not a timeline. None of these prerequisites are met today.

Shadow mode means: Loom receives the same input stream as the primary
runtime (OpenClaw), runs its own governance hooks, and discards output.
The only observable effect is a divergence report comparing Loom decisions
against the primary runtime's actual decisions. Zero production impact.

This gate exists so that shadow mode is never attempted on a foundation
that cannot support it. Every box must be checked before the first shadow
run.

---

## Repository Prerequisites

- [ ] `meridian-loom` repository created (public, MIT or Apache-2.0)
- [ ] `Cargo.toml` with workspace structure
  - workspace root with `loom-core`, `loom-cli`, `loom-shadow` crates
- [ ] CI workflow running `cargo build` and `cargo test` on push
  - GitHub Actions, triggered on push and PR to `main`
- [ ] README with honest status: "Phase 0 -- no functional code yet"
  - No aspirational feature lists; only what exists and what does not

---

## Kernel-Side Prerequisites

- [ ] Stable `agent_identity` hook interface documented
  - exists in `RUNTIME_CONTRACT.md`
  - input: agent ID, runtime binding, registry snapshot
  - output: accept / reject / suspend with reason
- [ ] Stable `action_envelope` hook interface documented
  - exists in `RUNTIME_CONTRACT.md`
  - input: action payload, agent context, policy snapshot
  - output: signed envelope with governance metadata
- [ ] `kernel/runtimes.json` entry for `meridian_loom`
  - EXISTS today -- 0/7 hooks satisfied, status "planned"
- [ ] Shadow mode event format defined
  - envelope schema for shadowed actions
  - must include: timestamp, hook name, primary decision, shadow decision
  - must include: input hash for reproducibility
- [ ] Shadow divergence comparison script
  - compares Loom governance decisions against primary runtime
  - reads paired events and reports match / mismatch per hook

---

## Runtime Prerequisites

- [ ] Rust toolchain installed on build host
  - stable channel, minimum edition 2021
- [ ] `contract_bridge.rs`
  - reads `kernel/agent_registry.json`
  - maps agent IDs to Loom internal representation
  - validates registry schema before accepting
- [ ] `envelope.rs`
  - constructs action envelopes matching kernel format
  - serializes to JSON matching `action_envelope` hook output spec
- [ ] `lifecycle.rs`
  - start command: initialize runtime, load config, bind to event stream
  - health command: return structured status
  - stop command: graceful shutdown, flush pending shadow events
- [ ] Shadow mode receiver
  - accepts same input stream as OpenClaw
  - runs hooks (`agent_identity`, `action_envelope`)
  - discards governance output (does not affect production)
  - writes shadow event log to local file

---

## Verification Prerequisites

- [ ] `loom health` returns structured JSON
  - fields: `version`, `uptime_seconds`, `mode` ("shadow"), `hooks_active`
  - nonzero uptime confirms process is running
- [ ] `loom contract` reads `runtimes.json` and reports satisfaction
  - expected initial output: 2/7 (`agent_identity` + `action_envelope`)
  - remaining 5 hooks listed as null/unsatisfied
- [ ] `loom shadow report` compares governance events
  - reads shadow event log and primary runtime log
  - reports: total events, matches, divergences, divergence percentage
- [ ] 3+ consecutive shadow runs with zero governance divergence
  - each run processes at least 10 governance events
  - zero divergence across all three runs
  - logs retained as evidence artifacts

---

## What This Document Is Not

- Not a timeline or sprint plan.
  There are no dates here because dates without prerequisites are fiction.
- Not a claim that any prerequisite is met.
  Every box above is unchecked. That is the truth as of this writing.
- Not a Rust tutorial.
  The runtime prerequisites assume familiarity with Rust and Cargo.
- Not an architecture document.
  Architecture decisions belong in the Loom repo once it exists.

This is the gate checklist for Loom Phase 1 entry.
No box, no entry.
