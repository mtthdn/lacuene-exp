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
GET /api/enrichment/gap-candidates?min_score=4&limit=10
GET /api/enrichment/coverage-matrix      Full per-gene x per-source boolean matrix
GET /api/enrichment/provenance           Derivation audit trail
```

## Overnight Pipeline

`workers/overnight.sh` runs weekly (cron: `0 2 * * 0`), 4 phases:

| Phase | Worker | What |
|-------|--------|------|
| 1 | `bulk_hgnc.py` | Refresh HGNC gene data (skips if <7d old) |
| 2 | `bulk_downloads.py` | Cross-reference HPO, Orphanet, OMIM |
| 3 | `derive_gap_candidates.py` | Identify research candidates |
| 4 | Status snapshot | Record pipeline health |

Logs to `logs/overnight_YYYYMMDD.log`. Status in `derived/pipeline_status.json`.

## Knowledge Graph (.kg/)

CUE-based audit trail following the finglonger pattern:

- `schema.cue` — Type definitions for derivations, insights, rejected approaches
- `derivations.cue` — What was computed, from what, with canon purity
- `insights.cue` — Discoveries worth recording (e.g., CUE scaling benchmarks)
- `rejected.cue` — Failed approaches with rationale (prevents repeating work)

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
