#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
if [ "$#" -ge 1 ]; then
  OUT_DIR="$1"
else
  OUT_DIR="$ROOT/artifacts/backup-ready-spice"
fi
NETLIST="$ROOT/sim/backup_transfer/backup_ready_residual_fault.cir"
PARAMS="$ROOT/sim/backup_transfer/backup_ready_spice_parameters.json"
CHECKER="$ROOT/sim/backup_transfer/check_spice_results.py"

command -v ngspice >/dev/null 2>&1 || {
  echo "ERROR: ngspice is required; no SPICE result was generated." >&2
  exit 127
}
mkdir -p "$OUT_DIR"
cp "$NETLIST" "$PARAMS" "$CHECKER" "$OUT_DIR/"
(
  cd "$OUT_DIR"
  ngspice -v > ngspice-version.txt
  ngspice -b -o backup_ready_residual_fault.log backup_ready_residual_fault.cir
  test -s backup_ready_residual_fault.raw
  test -s backup_ready_residual_fault.csv
  python3 check_spice_results.py backup_ready_residual_fault.csv summary.json
  sha256sum backup_ready_residual_fault.cir \
    backup_ready_spice_parameters.json \
    check_spice_results.py \
    backup_ready_residual_fault.raw \
    backup_ready_residual_fault.log \
    backup_ready_residual_fault.csv \
    summary.json \
    ngspice-version.txt > SHA256SUMS
  sha256sum -c SHA256SUMS
)

echo "SPICE artifacts retained in: $OUT_DIR"
