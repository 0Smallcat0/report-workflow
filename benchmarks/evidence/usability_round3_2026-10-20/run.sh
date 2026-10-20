#!/bin/bash
# usage: run.sh TASK.py LOGNAME [PYTHONPATH-src]   -> runs drive.py into a scratch dir, log under logs/
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../../.." && pwd)
TASK=$1; LOG=$2; SRCPATH=${3:-$REPO/src}
OUT=${OUT:-$(mktemp -d)}
PYTHONPATH=$SRCPATH python "$REPO/benchmarks/evidence/usability_audit_2026-10-19/harness/drive.py" "$TASK" "$OUT" "$LOG" 2>&1 | grep -v findfont
