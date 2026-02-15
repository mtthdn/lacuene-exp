# lacuene-exp

Derived data layer for [lacuene](https://github.com/mtthdn/lacuene).

Follows the [finglonger pattern](https://finglonger.quique.ca): curated core stays
in lacuene (95 literature-verified genes, CUE lattice model), this repo provides
expanded data, derived insights, and an API that serves both.

## Architecture

```
lacuene (curated, 95 genes)             lacuene-exp (derived, 494+ genes)
├── model/*.cue   CUE unification       ├── expanded/   HGNC gene sets
├── output/       JSON projections       ├── derived/    Computed insights
└── data/         API caches             ├── api/        Flask REST API
                                         ├── workers/    Overnight pipeline
                                         └── .kg/        CUE audit trail
```

Separation of concerns: source routes (`/api/*`) serve curated data unchanged.
Enrichment routes (`/api/enrichment/*`) serve derived data with provenance metadata.
If derived data isn't available, the API falls back gracefully to curated.

## Data Tiers

| Tier | Genes | Source | Canon Purity |
|------|-------|--------|-------------|
| Curated | 95 | Literature-verified GRN | pure |
| Expanded | 494 | HGNC gene groups + name terms (ZNF excluded) | mixed |
| Genome-wide | 1,254 | Full craniofacial-adjacent HGNC set | derived |

## API Endpoints

### Source (curated data, from lacuene)
```
GET /api/status                   Health check + tier availability
GET /api/genes                    Curated 95 genes
GET /api/genes?tier=expanded      Expanded 494 genes
GET /api/genes?tier=genome        Bulk 1,254 genes
GET /api/genes/{symbol}           Single gene detail (curated or expanded)
GET /api/gaps                     Research gap report
GET /api/coverage                 Source coverage summary
```

### Enrichment (derived data, from overnight pipeline)
```
GET /api/enrichment/gap-candidates       Genes with disease signal not in curated set
GET /api/enrichment/gap-candidates?min_score=12&limit=10
GET /api/enrichment/coverage-matrix      Full per-gene x per-source boolean matrix
GET /api/enrichment/provenance           Derivation audit trail
```

### Digest
```
GET /api/digest                          Weekly digest as JSON
GET /api/digest?format=md                Weekly digest as raw markdown
```

## Overnight Pipeline

`workers/overnight.sh` runs weekly (cron: `0 2 * * 0`), 6 phases:

| Phase | Worker | What |
|-------|--------|------|
| 1 | `bulk_hgnc.py` | Refresh HGNC gene data (skips if <7d old) |
| 2 | `bulk_downloads.py` | Cross-reference HPO, Orphanet, OMIM |
| 3 | `derive_gap_candidates.py` | Identify research candidates (log-scaled scoring) |
| 4 | `enrich_candidates.py` | PubMed/UniProt enrichment for top 20 candidates |
| 5 | Status snapshot | Record pipeline health to `derived/pipeline_status.json` |
| 6 | `post_digest.sh` | Post markdown digest to GitHub issue (requires `GITHUB_TOKEN`) |

Logs to `logs/overnight_YYYYMMDD.log`. Status in `derived/pipeline_status.json`.

## Knowledge Graph (.kg/)

CUE-based audit trail following the finglonger pattern:

- `schema.cue` — Type definitions for derivations, insights, rejected approaches
- `derivations.cue` — What was computed, from what, with canon purity
- `insights.cue` — Discoveries worth recording (e.g., CUE scaling benchmarks)
- `rejected.cue` — Failed approaches with rationale (prevents repeating work)

## Testing

```bash
python3 -m pytest tests/ -v    # 25 tests: API routes + scoring formula
```

Tests cover all API routes (status codes, response shapes, filter params, graceful
degradation) and the gap candidate confidence scoring formula (monotonicity,
thresholds, known-value validation).

## Quick Start

```bash
# Prerequisites
pip install flask

# Generate curated data (in lacuene)
cd ../lacuene && just generate

# Run overnight pipeline (in lacuene-exp)
cd ../lacuene-exp
LACUENE_PATH=../lacuene ./workers/overnight.sh

# Start API
LACUENE_PATH=../lacuene python3 api/serve.py --port 5000

# Run tests
python3 -m pytest tests/ -v
```

## Deployment

Production runs on tulip (Proxmox), fully containerized:

| Component | Container | Address | Notes |
|-----------|-----------|---------|-------|
| API server | LXC 638 | lacuene-api.apercue.ca | gunicorn via systemd `lacuene-api.service` |
| Reverse proxy | LXC 612 | lacuene-api.apercue.ca | Caddy HTTP reverse proxy |
| Static site | LXC 612 | lacuene.apercue.ca | From lacuene `just site` output |
| Overnight cron | LXC 638 | Sunday 2 AM + daily git pull | `/etc/cron.d/lacuene-overnight` |

Nothing runs on the Proxmox host itself — all services are inside LXC containers.

```bash
# Manual deployment (inside LXC 638)
systemctl restart lacuene-api    # Restart API
journalctl -u lacuene-api -f     # Follow logs

# From tulip host
pct exec 638 -- systemctl status lacuene-api
```

## Canon Purity

Every derived dataset includes `_provenance` metadata:
```json
{
  "_provenance": {
    "worker": "workers/derive_gap_candidates.py",
    "generated": "2026-02-14T19:59:08Z",
    "canon_purity": "derived",
    "canon_sources": ["HGNC", "HPO", "Orphanet", "OMIM"],
    "non_canon_elements": ["Confidence scoring formula", "ZNF exclusion rule"]
  }
}
```

This tells consumers exactly what to trust and what's computed inference.
