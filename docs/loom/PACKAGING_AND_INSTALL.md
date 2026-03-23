# Meridian Loom — Packaging and Installation Strategy

**Status:** Design document (no implementation yet)

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
# Install kernel (Python, no build step)
git clone https://github.com/<org>/meridian-kernel.git
cd meridian-kernel && pip install -e .   # or just use directly

# Install Loom (Rust)
git clone https://github.com/<org>/meridian-loom.git
cd meridian-loom && cargo build --release

# Point Loom at kernel
loom config set kernel_path /path/to/meridian-kernel
```

In **embedded mode** (see `CLI_AND_MODES.md`), Loom ships a vendored copy of
the kernel's governance checks as a compiled library. But the canonical install
path keeps them separate.

## Versioning

Loom versions independently from the kernel. The contract spec version
(from `runtimes.json`) is the compatibility anchor:

```
Kernel contract spec: v1.0
Loom version: 0.1.0 (implements contract spec v1.0, 2/7 hooks proven)
```

Loom's version number does not imply kernel version compatibility beyond
the stated contract spec version.
