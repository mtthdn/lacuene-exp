#!/usr/bin/env python3
"""
Bulk HGNC gene downloader.

Downloads the complete HGNC protein-coding gene set (~19K genes) and provides
lookup utilities for the bulk analysis pipeline.

Output: data/hgnc/hgnc_complete.json (full dataset)
        data/hgnc/hgnc_protein_coding.json (filtered to protein-coding)

The HGNC complete set includes: symbol, name, locus_group, locus_type,
NCBI Gene ID, UniProt ID, Ensembl ID, OMIM ID, and more.

Usage:
    python3 normalizers/bulk_hgnc.py                    # Download full set
    python3 normalizers/bulk_hgnc.py --craniofacial     # Filter to craniofacial-adjacent
    python3 normalizers/bulk_hgnc.py --stats             # Print stats only
"""

import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CACHE_DIR = REPO_ROOT / "data" / "hgnc"
FULL_CACHE = CACHE_DIR / "hgnc_complete.json"
PROTEIN_CODING_CACHE = CACHE_DIR / "hgnc_protein_coding.json"

# HGNC REST API — returns all protein-coding genes
HGNC_SEARCH_URL = (
    "https://rest.genenames.org/search/locus_type:%22gene+with+protein+product%22"
    "?rows=25000"
)

# HGNC fetch for full records with cross-references
HGNC_FETCH_URL = "https://rest.genenames.org/fetch/symbol/{symbol}"

# Alternative: bulk download TSV
HGNC_BULK_URL = (
    "https://storage.googleapis.com/public-download-files/hgnc/"
    "json/json/hgnc_complete_set.json"
)


def download_hgnc_complete() -> dict:
    """Download the full HGNC complete set JSON."""
    print("Downloading HGNC complete set...")
    req = urllib.request.Request(
        HGNC_BULK_URL,
        headers={"Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"  Downloaded {len(data.get('response', {}).get('docs', []))} genes")
            return data
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"  ERROR: download failed: {e}", file=sys.stderr)
        sys.exit(1)


def filter_protein_coding(hgnc_data: dict) -> list[dict]:
    """Filter to protein-coding genes with status 'Approved'."""
    docs = hgnc_data.get("response", {}).get("docs", [])
    filtered = []
    for doc in docs:
        if (doc.get("locus_group") == "protein-coding gene"
                and doc.get("status") == "Approved"):
            filtered.append({
                "symbol": doc.get("symbol", ""),
                "name": doc.get("name", ""),
                "hgnc_id": doc.get("hgnc_id", ""),
                "ncbi_id": str(doc.get("entrez_id", "")),
                "ensembl_id": doc.get("ensembl_gene_id", ""),
                "uniprot_id": (doc.get("uniprot_ids") or [""])[0],
                "omim_id": str((doc.get("omim_id") or [""])[0]) if doc.get("omim_id") else "",
                "locus_type": doc.get("locus_type", ""),
                "gene_group": doc.get("gene_group", []),
                "location": doc.get("location", ""),
            })
    return filtered


def build_lookup(genes: list[dict]) -> dict:
    """Build a lookup dict keyed by symbol."""
    return {g["symbol"]: g for g in genes}


def find_craniofacial_genes(genes: list[dict], curated_symbols: set) -> list[dict]:
    """
    Identify craniofacial-adjacent genes beyond the curated set.

    Strategy:
    1. All curated genes (already in genes.py)
    2. Genes in craniofacial-related gene groups (HGNC gene_group field)
    3. Genes with craniofacial-related terms in their name
    """
    craniofacial_groups = {
        "Bone morphogenetic proteins",
        "Fibroblast growth factors",
        "Fibroblast growth factor receptors",
        "Hedgehog signaling molecule",
        "Homeobox genes",
        "Paired box genes",
        "SRY-boxes",
        "T-boxes",
        "Forkhead boxes",
        "SMAD family",
        "Transforming growth factor beta",
        "Wingless-type MMTV integration site family",
        "WNT signaling pathway",
        "Notch receptors",
        "Cadherins",
        "Collagens",
        "Matrix metallopeptidases",
        "Disintegrin and metallopeptidase domain",
        "Ephrin receptors",
        "Semaphorins",
        "Twist family",
        "Snail family",
        "Zinc fingers C2H2-type",
        "Endothelin receptors",
        "Gap junction proteins",
        "Runt-related transcription factors",
        "Retinoid receptors",
    }

    craniofacial_name_terms = {
        "cranio", "facial", "palate", "cleft", "dental", "tooth",
        "mandib", "maxill", "neural crest", "branchial",
        "pharyngeal", "otic", "skeletal", "cartilage", "chondro",
        "osteo", "bone morpho", "craniofacial",
    }

    results = []
    seen = set()

    for gene in genes:
        sym = gene["symbol"]
        if sym in seen:
            continue

        # Always include curated genes
        if sym in curated_symbols:
            gene["source"] = "curated"
            results.append(gene)
            seen.add(sym)
            continue

        # Check gene groups
        groups = gene.get("gene_group", [])
        matched_group = False
        for group in groups:
            if any(cg.lower() in group.lower() for cg in craniofacial_groups):
                gene["source"] = f"group:{group}"
                results.append(gene)
                seen.add(sym)
                matched_group = True
                break

        if matched_group:
            continue

        # Check name terms
        name_lower = gene.get("name", "").lower()
        for term in craniofacial_name_terms:
            if term in name_lower:
                gene["source"] = f"name:{term}"
                results.append(gene)
                seen.add(sym)
                break

    return results


def print_stats(protein_coding: list[dict], craniofacial: list[dict] = None):
    """Print summary statistics."""
    print(f"\nHGNC Statistics:")
    print(f"  Protein-coding genes: {len(protein_coding)}")
    print(f"  With NCBI ID:         {sum(1 for g in protein_coding if g['ncbi_id'])}")
    print(f"  With UniProt ID:      {sum(1 for g in protein_coding if g['uniprot_id'])}")
    print(f"  With Ensembl ID:      {sum(1 for g in protein_coding if g['ensembl_id'])}")
    print(f"  With OMIM ID:         {sum(1 for g in protein_coding if g['omim_id'])}")

    if craniofacial:
        print(f"\n  Craniofacial-adjacent: {len(craniofacial)}")
        sources = {}
        for g in craniofacial:
            src = g.get("source", "unknown").split(":")[0]
            sources[src] = sources.get(src, 0) + 1
        for src, count in sorted(sources.items(), key=lambda x: -x[1]):
            print(f"    {src}: {count}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="HGNC bulk gene downloader")
    parser.add_argument("--craniofacial", action="store_true",
                        help="Filter to craniofacial-adjacent genes")
    parser.add_argument("--stats", action="store_true",
                        help="Print statistics only")
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if cached")
    args = parser.parse_args()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Download or load cached
    if FULL_CACHE.exists() and not args.force:
        print(f"Loading cached HGNC data from {FULL_CACHE}")
        with open(FULL_CACHE) as f:
            hgnc_data = json.load(f)
    else:
        hgnc_data = download_hgnc_complete()
        with open(FULL_CACHE, "w") as f:
            json.dump(hgnc_data, f)
        print(f"  Cached to {FULL_CACHE}")

    # Filter to protein-coding
    protein_coding = filter_protein_coding(hgnc_data)

    # Save filtered set
    with open(PROTEIN_CODING_CACHE, "w") as f:
        json.dump(protein_coding, f, indent=2)
    print(f"  {len(protein_coding)} protein-coding genes -> {PROTEIN_CODING_CACHE}")

    if args.craniofacial:
        # Load current curated set
        sys.path.insert(0, str(REPO_ROOT / "normalizers"))
        from genes import GENES
        curated_symbols = set(GENES.keys())

        craniofacial = find_craniofacial_genes(protein_coding, curated_symbols)

        outfile = CACHE_DIR / "hgnc_craniofacial.json"
        with open(outfile, "w") as f:
            json.dump(craniofacial, f, indent=2)
        print(f"  {len(craniofacial)} craniofacial-adjacent genes -> {outfile}")

        print_stats(protein_coding, craniofacial)
    elif args.stats:
        print_stats(protein_coding)
    else:
        print_stats(protein_coding)


if __name__ == "__main__":
    main()
