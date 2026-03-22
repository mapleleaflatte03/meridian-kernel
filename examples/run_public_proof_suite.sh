#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "== OpenClaw Federation Proof =="
python3 "$ROOT_DIR/kernel/tests/test_openclaw_federation_proof.py"

echo "== Three-Host Federation Proof =="
python3 "$ROOT_DIR/kernel/tests/test_three_host_federation_proof.py"
