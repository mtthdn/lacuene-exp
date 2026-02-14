#!/usr/bin/env python3
"""
Genome-wide bulk pipeline: Python-only analysis for all 19K protein-coding genes.

This bypasses CUE (too slow at scale) and produces CSV output by cross-referencing
bulk download sources that cover the entire genome:

  - HGNC: symbol, name, cross-reference IDs (NCBI, UniProt, Ensembl, OMIM)
  - HPO: phenotype-to-gene associations (bulk file)
  - Orphanet: rare disease associations (bulk XML, pre-cached)
  - OMIM: subset data (bundled JSON)

Sources that require per-gene API calls (GO, PubMed, ClinVar, gnomAD, etc.)
are not included. Use the curated CUE pipeline for those.

Output: output/bulk/genome_wide.csv
        output/bulk/genome_wide_summary.json

Usage:
    python3 normalizers/bulk_downloads.py
    python3 normalizers/bulk_downloads.py --craniofacial   # Only craniofacial genes
"""

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LACUENE_PATH = Path(os.environ.get("LACUENE_PATH", REPO_ROOT.parent / "lacuene"))
OUTPUT_DIR = REPO_ROOT / "derived"


def load_hgnc_genes(craniofacial_only: bool = False) -> list[dict]:
    """Load protein-coding genes from HGNC cache."""
    if craniofacial_only:
        filename = "hgnc_craniofacial.json"
    else:
        filename = "hgnc_protein_coding.json"
    # Check lacuene-exp/expanded first, then lacuene/data/hgnc
    path = REPO_ROOT / "expanded" / filename
    if not path.exists():
        path = LACUENE_PATH / "data" / "hgnc" / filename

    if not path.exists():
        print(f"ERROR: {path} not found. Run: python3 normalizers/bulk_hgnc.py",
              file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        return json.load(f)


def load_hpo_associations() -> dict[str, list[str]]:
    """Load HPO phenotype-to-gene bulk file. Returns {symbol: [phenotype_terms]}."""
    hpo_file = LACUENE_PATH / "data" / "hpo" / "genes_to_phenotype.txt"
    if not hpo_file.exists():
        print(f"  WARNING: {hpo_file} not found, skipping HPO", file=sys.stderr)
        return {}

    gene_phenos: dict[str, set[str]] = defaultdict(set)
    with open(hpo_file) as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 4:
                # Format: ncbi_gene_id, gene_symbol, hpo_id, hpo_term_name, ...
                symbol = parts[1]
                hpo_term = parts[3] if len(parts) > 3 else parts[2]
                gene_phenos[symbol].add(hpo_term)

    return {sym: sorted(terms) for sym, terms in gene_phenos.items()}


def load_orphanet_associations() -> dict[str, list[dict]]:
    """Load Orphanet rare disease associations from cache. Returns {symbol: [{disorder}]}."""
    cache_file = LACUENE_PATH / "data" / "orphanet" / "orphanet_cache.json"
    if not cache_file.exists():
        print(f"  WARNING: {cache_file} not found, skipping Orphanet", file=sys.stderr)
        return {}

    with open(cache_file) as f:
        cache = json.load(f)

    return cache


def load_omim_subset() -> dict[str, dict]:
    """Load bundled OMIM subset. Returns {symbol: {title, syndromes, inheritance}}."""
    omim_file = LACUENE_PATH / "data" / "omim" / "omim_subset.json"
    if not omim_file.exists():
        print(f"  WARNING: {omim_file} not found, skipping OMIM", file=sys.stderr)
        return {}

    with open(omim_file) as f:
        data = json.load(f)

    return data.get("genes", {})


def load_curated_sources() -> dict[str, dict]:
    """Load source coverage from the curated CUE pipeline (if available)."""
    sources_file = LACUENE_PATH / "output" / "sources.json"
    if not sources_file.exists():
        return {}

    with open(sources_file) as f:
        return json.load(f)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Genome-wide bulk analysis")
    parser.add_argument("--craniofacial", action="store_true",
                        help="Only craniofacial-adjacent genes")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load gene universe
    genes = load_hgnc_genes(craniofacial_only=args.craniofacial)
    gene_symbols = {g["symbol"] for g in genes}
    gene_lookup = {g["symbol"]: g for g in genes}
    print(f"Loaded {len(genes)} genes from HGNC")

    # Load bulk sources
    print("Loading bulk sources...")
    hpo = load_hpo_associations()
    orphanet = load_orphanet_associations()
    omim = load_omim_subset()
    curated = load_curated_sources()

    print(f"  HPO: {len(hpo)} genes with phenotypes")
    print(f"  Orphanet: {len(orphanet)} genes with disorders")
    print(f"  OMIM subset: {len(omim)} genes")
    print(f"  Curated coverage: {len(curated)} genes")

    # Build merged records
    rows = []
    for gene in sorted(genes, key=lambda g: g["symbol"]):
        sym = gene["symbol"]

        # HGNC data
        row = {
            "symbol": sym,
            "name": gene.get("name", ""),
            "ncbi_id": gene.get("ncbi_id", ""),
            "uniprot_id": gene.get("uniprot_id", ""),
            "ensembl_id": gene.get("ensembl_id", ""),
            "omim_id": gene.get("omim_id", ""),
            "location": gene.get("location", ""),
        }

        # HPO
        phenos = hpo.get(sym, [])
        row["hpo_phenotype_count"] = len(phenos)
        row["in_hpo"] = len(phenos) > 0

        # Orphanet
        orph = orphanet.get(sym, [])
        if isinstance(orph, dict):
            row["orphanet_disorder_count"] = len(orph.get("disorders", []))
        elif isinstance(orph, list):
            row["orphanet_disorder_count"] = len(orph)
        else:
            row["orphanet_disorder_count"] = 0
        row["in_orphanet"] = row["orphanet_disorder_count"] > 0

        # OMIM
        omim_entry = omim.get(sym, {})
        row["in_omim"] = bool(omim_entry)
        row["omim_title"] = omim_entry.get("title", "")
        row["omim_syndrome_count"] = len(omim_entry.get("syndromes", []))

        # Curated pipeline coverage (if available)
        cur = curated.get(sym, {})
        row["in_curated"] = bool(cur)
        if cur:
            row["curated_source_count"] = sum(1 for v in cur.values() if v)
        else:
            row["curated_source_count"] = 0

        # Craniofacial source (from bulk_hgnc)
        row["cf_source"] = gene.get("source", "")

        rows.append(row)

    # Write CSV
    csv_path = OUTPUT_DIR / "genome_wide.csv"
    fieldnames = [
        "symbol", "name", "ncbi_id", "uniprot_id", "ensembl_id", "omim_id",
        "location", "in_hpo", "hpo_phenotype_count", "in_orphanet",
        "orphanet_disorder_count", "in_omim", "omim_title",
        "omim_syndrome_count", "in_curated", "curated_source_count",
        "cf_source",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} genes to {csv_path}")

    # Summary stats
    summary = {
        "total_genes": len(rows),
        "in_hpo": sum(1 for r in rows if r["in_hpo"]),
        "in_orphanet": sum(1 for r in rows if r["in_orphanet"]),
        "in_omim": sum(1 for r in rows if r["in_omim"]),
        "in_curated": sum(1 for r in rows if r["in_curated"]),
        "with_phenotypes_and_no_curated": sum(
            1 for r in rows
            if r["hpo_phenotype_count"] > 5 and not r["in_curated"]
        ),
        "disease_genes_not_curated": sum(
            1 for r in rows
            if r["in_omim"] and not r["in_curated"]
        ),
    }

    # Add provenance metadata (finglonger pattern)
    summary["_provenance"] = {
        "worker": "workers/bulk_downloads.py",
        "generated": datetime.now(timezone.utc).isoformat(),
        "canon_purity": "derived",
        "canon_sources": ["HGNC", "HPO", "Orphanet", "OMIM"],
        "non_canon_elements": ["Cross-reference join logic", "Phenotype count thresholds"],
    }

    summary_path = OUTPUT_DIR / "genome_wide_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote summary to {summary_path}")
    print(f"\nSummary:")
    for key, val in summary.items():
        print(f"  {key}: {val}")


if __name__ == "__main__":
    main()
