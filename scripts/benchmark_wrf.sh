#!/usr/bin/env bash
# Run a *prepared* WRF integration and report wall-clock time.
# Requires current directory = dedicated WRF run directory, with real.exe
# already completed and wrfinput_d01 / wrfbdy_d01 in place.
set -Eeuo pipefail

NP="$(printenv WRF_NP || true)"
LOG_DIR="$(printenv PALMAS_LOG_DIR || true)"
if [[ -z "$NP" ]]; then NP=4; fi
if [[ -z "$LOG_DIR" ]]; then LOG_DIR="$PWD/palmas-benchmarks"; fi

if [[ ! "$NP" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: WRF_NP must be a positive integer." >&2
  exit 2
fi

if [[ "$#" -gt 0 && "$1" == "--check" ]]; then
  printf 'Current directory: %s\nMPI processes: %s\nLogs: %s\n' "$PWD" "$NP" "$LOG_DIR"
  echo "Preflight mode only; no atmospheric simulation started."
  exit 0
fi

if [[ ! -x "./wrf.exe" || ! -f "./wrfinput_d01" || ! -f "./wrfbdy_d01" ]]; then
  echo "ERROR: need wrf.exe, wrfinput_d01 and wrfbdy_d01 in the working directory." >&2
  echo "First execute WPS and real.exe; see docs/QUICKSTART.md" >&2
  exit 2
fi

if ! command -v mpirun >/dev/null 2>&1; then
  echo "ERROR: mpirun is not installed or in PATH." >&2
  exit 2
fi

mkdir -p "$LOG_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
log="$LOG_DIR/wrf_$stamp"_np"$NP".log
csv="$LOG_DIR/timings.csv"
start="$(date +%s)"

echo "WRF PALMAS: starting real WRF integration with $NP MPI ranks."
echo "Logs: $log"
set +e
mpirun -np "$NP" ./wrf.exe >"$log" 2>&1
status=$?
set -e

elapsed="$(( $(date +%s) - start ))"
success="no"
# WRF writes completion marker to rsl.out.0000 in dmpar mode.
if [[ "$status" -eq 0 ]] && [[ -f rsl.out.0000 ]] && grep -q 'SUCCESS COMPLETE WRF' rsl.out.0000; then
  success="yes"
fi
if [[ ! -f "$csv" ]]; then
  printf 'run_utc,mpi_ranks,elapsed_seconds,exit_code,success\n' > "$csv"
fi
printf '%s,%s,%s,%s,%s\n' "$stamp" "$NP" "$elapsed" "$status" "$success" >> "$csv"
echo "Wall clock: $elapsed seconds; successful completion: $success"
echo "Timing history: $csv"

if [[ "$success" != "yes" ]]; then
  echo "WRF did not report SUCCESS COMPLETE WRF. Inspect $log and rsl.error.0000." >&2
  exit 1
fi
