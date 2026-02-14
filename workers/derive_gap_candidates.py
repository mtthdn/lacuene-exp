#!/usr/bin/env python3
"""
Derive gap candidates: genes with strong disease signal not in the curated set.

Identifies craniofacial-adjacent genes that have:
  - 5+ HPO phenotypes, OR
  - Orphanet rare disease associations, OR
  - OMIM disease entries
...but are NOT in the curated 95-gene lacuene pipeline.

These are candidates for literature review and potential inclusion in the
curated set. The output includes a confidence score based on evidence density.

Output: derived/gap_candidates.json

Usage:
    LACUENE_PATH=../lacuene python3 workers/derive_gap_candidates.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LACUENE_PATH = Path(os.environ.get("LACUENE_PATH", REPO_ROOT.parent / "lacuene"))
OUTPUT_DIR = REPO_ROOT / "derived"


def load_json(path: Path, label: str) -> dict | list:
    if not path.exists():
        print(f"  [{label}] Not found: {path}", file=sys.stderr)
        return {}
    with open(path) as f:
        return json.load(f)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load expanded gene set
    expanded = load_json(REPO_ROOT / "expanded" / "hgnc_craniofacial.json", "expanded")
    if not expanded:
        print("ERROR: No expanded gene data. Run: python3 workers/bulk_hgnc.py --craniofacial",
              file=sys.stderr)
        sys.exit(1)

    # Filter ZNF
    expanded = [g for g in expanded if "Zinc fingers C2H2" not in str(g.get("source", ""))]
    expanded_lookup = {g["symbol"]: g for g in expanded}
    print(f"Loaded {len(expanded)} expanded genes (ZNF excluded)")

    # Load curated sources to know which genes are already tracked
    curated_sources = load_json(LACUENE_PATH / "output" / "sources.json", "curated")
    curated_symbols = set(curated_sources.keys()) if curated_sources else set()
    print(f"Curated set: {len(curated_symbols)} genes")

    # Load HPO phenotype associations
    hpo_genes = {}
    hpo_file = LACUENE_PATH / "data" / "hpo" / "genes_to_phenotype.txt"
    if hpo_file.exists():
        from collections import defaultdict
        gene_phenos = defaultdict(set)
        with open(hpo_file) as f:
            for line in f:
                if line.startswith("#"):
                    continue
                parts = line.strip().split("\t")
                if len(parts) >= 4:
                    gene_phenos[parts[1]].add(parts[3])
        hpo_genes = {sym: sorted(terms) for sym, terms in gene_phenos.items()}
        print(f"HPO: {len(hpo_genes)} genes with phenotypes")

    # Load Orphanet
    orphanet = load_json(LACUENE_PATH / "data" / "orphanet" / "orphanet_cache.json", "orphanet")

    # Load OMIM subset
    omim_data = load_json(LACUENE_PATH / "data" / "omim" / "omim_subset.json", "omim")
    omim_genes = omim_data.get("genes", {}) if isinstance(omim_data, dict) else {}

    # Find gap candidates — expanded genes NOT in curated set with disease signal
    candidates = []
    for gene in expanded:
        sym = gene["symbol"]
        if sym in curated_symbols:
            continue  # Already curated

        hpo_count = len(hpo_genes.get(sym, []))
        hpo_terms = hpo_genes.get(sym, [])[:10]  # Top 10 for display

        orph_data = orphanet.get(sym, {})
        if isinstance(orph_data, dict):
            orph_disorders = orph_data.get("disorders", [])
        elif isinstance(orph_data, list):
            orph_disorders = orph_data
        else:
            orph_disorders = []
        orph_count = len(orph_disorders)

        omim_entry = omim_genes.get(sym, {})
        has_omim = bool(omim_entry)
        omim_syndromes = len(omim_entry.get("syndromes", [])) if has_omim else 0

        # Confidence score: weighted by evidence type
        # HPO phenotypes: 1 point per 5 phenotypes (capped at 5)
        # Orphanet disorders: 3 points each (rare disease = high signal)
        # OMIM entry: 2 points + 1 per syndrome
        score = 0
        score += min(5, hpo_count // 5)  # Up to 5 points from HPO
        score += min(9, orph_count * 3)  # Up to 9 points from Orphanet
        score += (2 + omim_syndromes) if has_omim else 0  # 2+ from OMIM

        if score == 0:
            continue  # No disease signal at all

        candidates.append({
            "symbol": sym,
            "name": gene.get("name", ""),
            "hgnc_source": gene.get("source", ""),
            "gene_group": gene.get("gene_group", []),
            "location": gene.get("location", ""),
            "confidence_score": score,
            "evidence": {
                "hpo_phenotype_count": hpo_count,
                "hpo_top_terms": hpo_terms,
                "orphanet_disorder_count": orph_count,
                "orphanet_disorders": [
                    d.get("name", d) if isinstance(d, dict) else str(d)
                    for d in orph_disorders[:5]
                ],
                "has_omim": has_omim,
                "omim_title": omim_entry.get("title", "") if has_omim else "",
                "omim_syndrome_count": omim_syndromes,
            },
            "cross_references": {
                "ncbi_id": gene.get("ncbi_id", ""),
                "uniprot_id": gene.get("uniprot_id", ""),
                "omim_id": gene.get("omim_id", ""),
                "ensembl_id": gene.get("ensembl_id", ""),
            },
        })

    # Sort by confidence score descending
    candidates.sort(key=lambda c: c["confidence_score"], reverse=True)

    # Build output with provenance
    output = {
        "_provenance": {
            "worker": "workers/derive_gap_candidates.py",
            "generated": datetime.now(timezone.utc).isoformat(),
            "canon_purity": "derived",
            "canon_sources": ["HGNC", "HPO", "Orphanet", "OMIM"],
            "non_canon_elements": [
                "Confidence scoring formula",
                "ZNF exclusion rule",
                "Gene group matching heuristic",
            ],
            "description": "Genes with disease signal not in curated set — candidates for literature review",
        },
        "curated_count": len(curated_symbols),
        "expanded_count": len(expanded),
        "candidate_count": len(candidates),
        "score_distribution": {
            "high (8+)": sum(1 for c in candidates if c["confidence_score"] >= 8),
            "medium (4-7)": sum(1 for c in candidates if 4 <= c["confidence_score"] < 8),
            "low (1-3)": sum(1 for c in candidates if c["confidence_score"] < 4),
        },
        "candidates": candidates,
    }

    out_path = OUTPUT_DIR / "gap_candidates.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {len(candidates)} candidates to {out_path}")
    print(f"  High confidence (8+): {output['score_distribution']['high (8+)']}")
    print(f"  Medium (4-7):         {output['score_distribution']['medium (4-7)']}")
    print(f"  Low (1-3):            {output['score_distribution']['low (1-3)']}")

    # Show top 10
    if candidates:
        print(f"\nTop 10 candidates:")
        for c in candidates[:10]:
            hpo = c["evidence"]["hpo_phenotype_count"]
            orph = c["evidence"]["orphanet_disorder_count"]
            omim = "OMIM" if c["evidence"]["has_omim"] else ""
            print(f"  {c['symbol']:10s} score={c['confidence_score']:2d}  "
                  f"HPO={hpo:3d}  Orphanet={orph}  {omim}  {c['name'][:50]}")


if __name__ == "__main__":
    main()
