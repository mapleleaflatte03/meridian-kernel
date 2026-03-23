# Meridian Loom — Packaging and Installation Strategy

**Status:** Design document plus local experimental scaffold

## Build Requirements

| Component | Toolchain | Notes |
|-----------|-----------|-------|
| Rust supervisor | `cargo build --release` | Minimum Rust edition: 2021 |
| Python workers | Standard CPython 3.10+ | No exotic dependencies planned |
| TypeScript workers | Node 18+ / Bun | Channel adapter code |
| WASM modules | `cargo build --target wasm32-wasi` | Sandboxed capability modules |

## Distribution Formats

### 1. Source build (primary path during early phases)

```bash
git clone https://github.com/<org>/meridian-loom.git
cd meridian-loom
cargo build --release
```

Binary lands at `target/release/loom`. This is the expected path during
Phase 0–2 when the audience is the Meridian team and early contributors.

**Current truth:** a local experimental scaffold already exists and builds in
the founder workspace. Public GitHub publication of that repo is still pending.

### 2. Pre-built binary (Phase 3+)

When the ABI stabilizes, publish platform binaries:

| Platform | Format |
|----------|--------|
| Linux x86_64 | Tarball, `.deb`, `.rpm` |
| macOS arm64 | Tarball, Homebrew tap |
| macOS x86_64 | Tarball |
| Docker | `ghcr.io/<org>/meridian-loom:<tag>` |

No Windows target planned initially. Docker covers cross-platform needs
during early adoption.

### 3. Docker image

```dockerfile
FROM rust:1-slim AS build
WORKDIR /src
COPY . .
RUN cargo build --release

FROM debian:bookworm-slim
COPY --from=build /src/target/release/loom /usr/local/bin/loom
COPY loom.toml /etc/loom/loom.toml
ENTRYPOINT ["loom"]
CMD ["start"]
```

The Docker image bundles only the Rust supervisor binary and default config.
Workers (Python, TypeScript) are mounted or installed as additional layers
depending on the deployment.

### 4. Cargo install (convenience)

```bash
cargo install meridian-loom
```

Published to crates.io once the CLI surface stabilizes (Phase 3+).

## Configuration

All runtime config lives in `loom.toml`:

```toml
[runtime]
mode = "standalone"          # or "shadow", "embedded"
kernel_path = "/path/to/meridian-kernel"

[governance]
contract_bridge = true       # Enable 7-hook bridge to kernel
kernel_url = ""              # For remote kernel mode (future)

[transport]
telegram = false
mcp = false
http = true

[workers]
python_path = "workers/python"
typescript_path = "workers/typescript"
wasm_dir = "workers/wasm"

[scheduler]
cron_enabled = false
```

The config file is the single source of truth for what Loom does at startup.
No implicit behavior — if a transport isn't enabled in config, it isn't loaded.

## Kernel Dependency at Install Time

Loom does **not** bundle the kernel. The kernel is a separate install:

```bash
# Get kernel (pure Python, stdlib-only — no pip install needed)
git clone https://github.com/<org>/meridian-kernel.git

# Install Loom (Rust)
git clone https://github.com/<org>/meridian-loom.git
cd meridian-loom && cargo build --release

# Point Loom at kernel
loom config set kernel_path /path/to/meridian-kernel
```

In **embedded mode** (see `CLI_AND_MODES.md`), Loom is expected to ship a
vendored copy of the kernel's governance checks as a compiled library. The
current scaffold does not implement that bundling yet. The canonical install
path still keeps kernel and Loom separate.

## Versioning

Loom versions independently from the kernel. The seven-hook contract
defined in `kernel/runtimes.json` is the compatibility anchor — it does
not carry its own version number today. Compatibility is expressed as
the count of proven hooks:

```
Loom 0.1.0 — 0/7 hooks proven (Phase 0, spec + local scaffold)
Loom 0.2.0 — 2/7 hooks proven (Phase 1, shadow mode)
```

Loom's version number does not imply kernel version compatibility beyond
the hook count it has proven against the current contract definition.

## Maturity Gates

Loom follows a graduated maturity model. Each gate requires proof, not
just elapsed time.

| Gate | Requirement | What it unlocks |
|------|-------------|-----------------|
| **Pre-alpha** (current) | Spec exists, registry entry at 0/7, local scaffold builds | CLI/setup rehearsal only |
| **Alpha** | 2+/7 hooks proven, shadow mode runs | Evaluation by contributors |
| **Beta** | 5+/7 hooks proven, governed worker cells pass | Opt-in use alongside primary runtime |
| **GA** | 7/7 hooks proven, 7 consecutive clean night-shift runs | Production use, OpenClaw retirement eligible |

No gate is reached until the corresponding `contract_compliance` fields
in `runtimes.json` are set to `true` by passing tests. `null` = unproven.
