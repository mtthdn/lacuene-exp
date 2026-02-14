# lacuene-exp

Experimental derived data layer for [lacuene](https://github.com/mtthdn/lacuene).

Follows the finglonger pattern: curated core stays in lacuene (95 genes, CUE model),
this repo provides optional expanded data and API endpoints.

## Architecture

```
lacuene (curated, 95 genes)
  └── model/*.cue                    CUE lattice unification
  └── output/sources.json            Curated gene data

lacuene-exp (derived, 494+ genes)
  └── expanded/genes_expanded.json   HGNC-expanded gene set
  └── expanded/bulk_craniofacial.csv Cross-referenced bulk data
  └── api/                           Flask API serving both tiers
  └── workers/                       Overnight derivation scripts
```

## Tiers

| Tier | Genes | Source | Serves |
|------|-------|--------|--------|
| Curated | 95 | Literature-verified GRN | lacuene CUE model |
| Expanded | 494 | HGNC gene groups + name terms | API endpoint |
| Genome-wide | 1,254+ | Full craniofacial-adjacent | Bulk CSV |

## API (planned)

```
GET /api/genes                    → curated 95 genes
GET /api/genes?tier=expanded      → expanded 494 genes
GET /api/genes?tier=genome        → bulk 1,254 genes
GET /api/genes/{symbol}           → single gene, all sources
GET /api/gaps                     → research gap report
GET /api/coverage                 → source coverage matrix
```

Graceful degradation: if expanded data isn't available, API falls back to curated.

## Relationship to CKAN

Datasets can be registered in the UOttawa CKAN instance for catalog discovery.
