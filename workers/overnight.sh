#!/bin/bash
# lacuene-exp overnight derivation pipeline
#
# Follows finglonger pattern: phased execution with graceful degradation.
# Designed for cron: 0 2 * * 0  (2 AM Sunday, weekly)
#
# Phases:
#   1. Refresh HGNC data (network)
#   2. Cross-reference bulk sources (CPU)
#   3. Derive gap candidates (CPU)
#   4. Export for API (CPU)
#
# Usage:
#   ./workers/overnight.sh                  # Full run
#   LACUENE_PATH=/path/to/lacuene ./workers/overnight.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
DERIVED_DIR="$REPO_ROOT/derived"
LOG_DIR="$REPO_ROOT/logs"

export LACUENE_PATH="${LACUENE_PATH:-$(dirname "$REPO_ROOT")/lacuene}"

DATE=$(date +%Y%m%d)
mkdir -p "$LOG_DIR" "$DERIVED_DIR"
LOG="$LOG_DIR/overnight_${DATE}.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"
}

phase_start() {
    log "=== Phase $1: $2 ==="
}

phase_end() {
    log "=== Phase $1 complete (${SECONDS}s elapsed) ==="
}

# Check prerequisites
log "lacuene-exp overnight pipeline starting"
log "REPO_ROOT: $REPO_ROOT"
log "LACUENE_PATH: $LACUENE_PATH"
log "Python: $(python3 --version 2>&1)"

if [ ! -d "$LACUENE_PATH" ]; then
    log "ERROR: LACUENE_PATH not found: $LACUENE_PATH"
    exit 1
fi

SECONDS=0

# ── Phase 1: Refresh HGNC data ──────────────────────────────────────
phase_start 1 "HGNC refresh"

HGNC_CACHE="$REPO_ROOT/expanded/hgnc_craniofacial.json"
HGNC_AGE_DAYS=7

if [ -f "$HGNC_CACHE" ]; then
    AGE=$(python3 -c "import os,time; print(int((time.time()-os.path.getmtime('$HGNC_CACHE'))/86400))")
    if [ "$AGE" -lt "$HGNC_AGE_DAYS" ]; then
        log "HGNC cache is ${AGE}d old (threshold: ${HGNC_AGE_DAYS}d), skipping refresh"
    else
        log "HGNC cache is ${AGE}d old, refreshing..."
        python3 "$SCRIPT_DIR/bulk_hgnc.py" --craniofacial >> "$LOG" 2>&1 || {
            log "WARNING: HGNC refresh failed, using stale cache"
        }
    fi
else
    log "No HGNC cache found, downloading..."
    python3 "$SCRIPT_DIR/bulk_hgnc.py" --craniofacial >> "$LOG" 2>&1 || {
        log "ERROR: HGNC download failed"
        exit 1
    }
fi

phase_end 1

# ── Phase 2: Bulk cross-reference ───────────────────────────────────
phase_start 2 "Bulk cross-reference"

python3 "$SCRIPT_DIR/bulk_downloads.py" --craniofacial >> "$LOG" 2>&1 || {
    log "WARNING: Bulk cross-reference failed"
}

phase_end 2

# ── Phase 3: Derive gap candidates ──────────────────────────────────
phase_start 3 "Gap candidate derivation"

python3 "$SCRIPT_DIR/derive_gap_candidates.py" >> "$LOG" 2>&1 || {
    log "WARNING: Gap candidate derivation failed"
}

phase_end 3

# ── Phase 4: Pipeline status ────────────────────────────────────────
phase_start 4 "Status snapshot"

# Write pipeline status JSON
cat > "$DERIVED_DIR/pipeline_status.json" << STATUSEOF
{
  "last_run": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "duration_seconds": $SECONDS,
  "phases": {
    "hgnc_refresh": "$([ -f "$HGNC_CACHE" ] && echo 'ok' || echo 'failed')",
    "bulk_crossref": "$([ -f "$DERIVED_DIR/genome_wide.csv" ] && echo 'ok' || echo 'failed')",
    "gap_candidates": "$([ -f "$DERIVED_DIR/gap_candidates.json" ] && echo 'ok' || echo 'failed')"
  },
  "files": {
    "hgnc_craniofacial": "$(wc -c < "$REPO_ROOT/expanded/hgnc_craniofacial.json" 2>/dev/null || echo 0)",
    "genome_wide_csv": "$(wc -c < "$DERIVED_DIR/genome_wide.csv" 2>/dev/null || echo 0)",
    "gap_candidates": "$(wc -c < "$DERIVED_DIR/gap_candidates.json" 2>/dev/null || echo 0)"
  }
}
STATUSEOF

phase_end 4

log "Pipeline complete in ${SECONDS}s"
log "Log: $LOG"
