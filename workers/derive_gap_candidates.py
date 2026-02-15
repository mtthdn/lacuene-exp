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
import math
import os
import sys
import xml.etree.ElementTree as ET
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

    # Load Orphanet from bulk XML (covers all 4500+ genes, not just curated 80)
    orphanet = {}
    orphanet_xml = LACUENE_PATH / "data" / "orphanet" / "en_product6.xml"
    orphanet_url = "http://www.orphadata.org/data/xml/en_product6.xml"
    if not orphanet_xml.exists():
        print(f"  Orphanet XML not cached, downloading from {orphanet_url}...")
        try:
            import urllib.request
            orphanet_xml.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(orphanet_url, str(orphanet_xml))
            print(f"  Downloaded {orphanet_xml.stat().st_size // 1024}KB")
        except Exception as e:
            print(f"  [Orphanet] Download failed: {e}", file=sys.stderr)
    if orphanet_xml.exists():
        tree = ET.parse(str(orphanet_xml))
        xml_root = tree.getroot()
        for disorder in xml_root.iter("Disorder"):
            orpha_code_el = disorder.find("OrphaCode")
            name_el = disorder.find("Name")
            if orpha_code_el is None or name_el is None:
                continue
            orpha_code = orpha_code_el.text or ""
            disorder_name = name_el.text or ""
            for assoc in disorder.iter("DisorderGeneAssociation"):
                gene_el = assoc.find("Gene")
                if gene_el is None:
                    continue
                symbol_el = gene_el.find("Symbol")
                if symbol_el is None or not symbol_el.text:
                    continue
                symbol = symbol_el.text.strip()
                if symbol not in orphanet:
                    orphanet[symbol] = {"disorders": []}
                existing = {d["orpha_code"] for d in orphanet[symbol]["disorders"]}
                if orpha_code not in existing:
                    orphanet[symbol]["disorders"].append(
                        {"orpha_code": orpha_code, "name": disorder_name}
                    )
        print(f"Orphanet: {len(orphanet)} genes from product6 XML")
    else:
        print(f"  [Orphanet] XML not available, skipping", file=sys.stderr)

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

        # Confidence score: log-scaled by evidence density
        # HPO: log2(count + 1) — 360 phenos → 8.5, 25 → 4.7, 5 → 2.6
        # Orphanet: log2(count + 1) × 3 — premium for rare disease signal
        #   18 disorders → 12.3, 5 → 7.8, 1 → 3.0
        # OMIM: 2 base + log2(syndromes + 1)
        score = 0.0
        score += math.log2(hpo_count + 1) if hpo_count > 0 else 0
        score += math.log2(orph_count + 1) * 3 if orph_count > 0 else 0
        score += (2 + math.log2(omim_syndromes + 1)) if has_omim else 0
        score = round(score, 1)

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
            "high (12+)": sum(1 for c in candidates if c["confidence_score"] >= 12),
            "medium (7-11.9)": sum(1 for c in candidates if 7 <= c["confidence_score"] < 12),
            "low (<7)": sum(1 for c in candidates if c["confidence_score"] < 7),
        },
        "candidates": candidates,
    }

    out_path = OUTPUT_DIR / "gap_candidates.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {len(candidates)} candidates to {out_path}")
    print(f"  High confidence (12+): {output['score_distribution']['high (12+)']}")
    print(f"  Medium (7-11.9):       {output['score_distribution']['medium (7-11.9)']}")
    print(f"  Low (<7):              {output['score_distribution']['low (<7)']}")

    # Show top 10
    if candidates:
        print(f"\nTop 10 candidates:")
        for c in candidates[:10]:
            hpo = c["evidence"]["hpo_phenotype_count"]
            orph = c["evidence"]["orphanet_disorder_count"]
            omim = "OMIM" if c["evidence"]["has_omim"] else ""
            print(f"  {c['symbol']:10s} score={c['confidence_score']:5.1f}  "
                  f"HPO={hpo:3d}  Orphanet={orph}  {omim}  {c['name'][:50]}")


if __name__ == "__main__":
    main()
