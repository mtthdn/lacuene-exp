#!/usr/bin/env python3
"""
Lightweight enrichment for gap candidates.

Fetches basic data from public APIs for top gap candidates without
adding them to the curated pipeline. Results go to derived/candidate_enrichment.json.

This is NOT the full 16-source normalizer pipeline — it's quick lookups
to help researchers evaluate whether candidates merit curation.

Sources queried:
  - NCBI Gene summary (via Entrez)
  - PubMed craniofacial publication count
  - UniProt function annotation

Usage:
    python3 workers/enrich_candidates.py
    python3 workers/enrich_candidates.py --top 10
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LACUENE_PATH = Path(os.environ.get("LACUENE_PATH", REPO_ROOT.parent / "lacuene"))
DERIVED_DIR = REPO_ROOT / "derived"


def fetch_json(url: str, timeout: int = 15) -> dict | None:
    """Fetch JSON from URL with retry."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            if attempt < 2:
                time.sleep(1 + attempt)
    return None


def fetch_gene_summary(ncbi_id: str) -> str:
    """Get gene summary from NCBI Entrez."""
    if not ncbi_id:
        return ""
    url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        f"?db=gene&id={ncbi_id}&retmode=json"
    )
    data = fetch_json(url)
    if not data:
        return ""
    result = data.get("result", {})
    gene_data = result.get(ncbi_id, {})
    return gene_data.get("summary", "")


def fetch_pubmed_count(symbol: str) -> int:
    """Count PubMed articles for gene + craniofacial."""
    url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=pubmed&term={symbol}+AND+(craniofacial+OR+neural+crest)"
        f"&retmode=json&retmax=0"
    )
    data = fetch_json(url)
    if not data:
        return 0
    return int(data.get("esearchresult", {}).get("count", 0))


def fetch_uniprot_function(uniprot_id: str) -> str:
    """Get function annotation from UniProt."""
    if not uniprot_id:
        return ""
    url = f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.json"
    data = fetch_json(url)
    if not data:
        return ""
    comments = data.get("comments", [])
    for c in comments:
        if c.get("commentType") == "FUNCTION":
            texts = c.get("texts", [])
            if texts:
                return texts[0].get("value", "")
    return ""


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Enrich gap candidates")
    parser.add_argument("--top", type=int, default=20, help="Number of top candidates")
    args = parser.parse_args()

    # Load gap candidates
    gc_path = DERIVED_DIR / "gap_candidates.json"
    if not gc_path.exists():
        print("ERROR: gap_candidates.json not found. Run derive_gap_candidates.py first.",
              file=sys.stderr)
        sys.exit(1)

    with open(gc_path) as f:
        gc_data = json.load(f)

    candidates = sorted(
        gc_data.get("candidates", []),
        key=lambda c: (-c.get("confidence_score", 0),
                       -c.get("evidence", {}).get("hpo_phenotype_count", 0))
    )[:args.top]

    print(f"Enriching top {len(candidates)} gap candidates...")

    enriched = []
    for i, c in enumerate(candidates):
        sym = c["symbol"]
        xref = c.get("cross_references", {})
        ncbi_id = xref.get("ncbi_id", "")
        uniprot_id = xref.get("uniprot_id", "")

        print(f"  [{i+1}/{len(candidates)}] {sym}...", end=" ", flush=True)

        summary = fetch_gene_summary(ncbi_id)
        pub_count = fetch_pubmed_count(sym)
        function = fetch_uniprot_function(uniprot_id)

        enriched.append({
            "symbol": sym,
            "confidence_score": c.get("confidence_score", 0),
            "ncbi_id": ncbi_id,
            "uniprot_id": uniprot_id,
            "gene_summary": summary[:500] if summary else "",
            "pubmed_craniofacial_count": pub_count,
            "uniprot_function": function[:500] if function else "",
            "hpo_phenotype_count": c.get("evidence", {}).get("hpo_phenotype_count", 0),
            "orphanet_disorder_count": c.get("evidence", {}).get("orphanet_disorder_count", 0),
            "cf_source": c.get("cf_source", ""),
        })

        # Rate limiting
        time.sleep(0.4)
        print(f"pubs={pub_count}")

    output = {
        "enriched_count": len(enriched),
        "candidates": enriched,
        "_provenance": {
            "worker": "workers/enrich_candidates.py",
            "generated": datetime.now(timezone.utc).isoformat(),
            "canon_purity": "derived",
            "canon_sources": ["NCBI Gene", "PubMed", "UniProt"],
            "non_canon_elements": ["Gene summary truncation", "Craniofacial search term filter"],
        },
    }

    out_path = DERIVED_DIR / "candidate_enrichment.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {len(enriched)} enriched candidates to {out_path}")

    # Print summary
    with_pubs = sum(1 for e in enriched if e["pubmed_craniofacial_count"] > 0)
    print(f"  {with_pubs}/{len(enriched)} have craniofacial publications")
    top3 = sorted(enriched, key=lambda e: -e["pubmed_craniofacial_count"])[:3]
    for e in top3:
        print(f"    {e['symbol']}: {e['pubmed_craniofacial_count']} craniofacial pubs")


if __name__ == "__main__":
    main()
