#!/usr/bin/env python3
"""
lacuene-exp API server.

Serves gene data at three tiers (curated, expanded, genome-wide).
Reads curated data from lacuene output, expanded from local files.

Follows the finglonger pattern: enhanced data is optional, core always works.

Usage:
    python3 api/serve.py                          # Default: port 5000
    python3 api/serve.py --port 8080
    LACUENE_PATH=/path/to/lacuene python3 api/serve.py
"""

import json
import os
import sys
from pathlib import Path

try:
    from flask import Flask, jsonify, request, abort
except ImportError:
    print("Flask required: pip install flask", file=sys.stderr)
    sys.exit(1)

app = Flask(__name__)

# Paths — curated data comes from lacuene, expanded from this repo
REPO_ROOT = Path(__file__).resolve().parent.parent
LACUENE_PATH = Path(os.environ.get("LACUENE_PATH", REPO_ROOT.parent / "lacuene"))
EXPANDED_DIR = REPO_ROOT / "expanded"

# Data stores (loaded at startup)
_curated_sources = {}    # symbol -> {source_flags}
_curated_gaps = {}       # gap report
_expanded_genes = []     # HGNC expanded gene list
_bulk_genes = []         # genome-wide craniofacial


def _load_json(path: Path, label: str) -> dict | list:
    """Load JSON file with graceful fallback."""
    if not path.exists():
        print(f"  [{label}] Not found: {path} (will serve without)")
        return {}
    with open(path) as f:
        data = json.load(f)
    print(f"  [{label}] Loaded {path.name}: {len(data) if isinstance(data, (list, dict)) else '?'} entries")
    return data


def load_data():
    """Load all data tiers at startup."""
    global _curated_sources, _curated_gaps, _expanded_genes, _bulk_genes

    print("Loading data tiers...")

    # Tier 1: Curated (from lacuene output)
    _curated_sources = _load_json(LACUENE_PATH / "output" / "sources.json", "curated")
    _curated_gaps = _load_json(LACUENE_PATH / "output" / "gap_report.json", "gaps")

    # Tier 2: Expanded (from this repo)
    _expanded_genes = _load_json(EXPANDED_DIR / "hgnc_craniofacial.json", "expanded")

    # Filter out ZNF for expanded tier
    if _expanded_genes:
        _expanded_genes = [g for g in _expanded_genes
                           if "Zinc fingers C2H2" not in str(g.get("source", ""))]
        print(f"  [expanded] After ZNF filter: {len(_expanded_genes)} genes")

    # Tier 3: Genome-wide (bulk CSV summary, if available)
    bulk_summary = _load_json(
        LACUENE_PATH / "output" / "bulk" / "genome_wide_summary.json", "bulk"
    )
    if bulk_summary:
        _bulk_genes = bulk_summary

    tiers = []
    if _curated_sources:
        tiers.append(f"curated({len(_curated_sources)})")
    if _expanded_genes:
        tiers.append(f"expanded({len(_expanded_genes)})")
    if _bulk_genes:
        tiers.append("bulk")
    print(f"  Ready: {', '.join(tiers) or 'no data loaded'}")


# --- Routes ---

@app.route("/api/status")
def status():
    """Health check with tier availability."""
    return jsonify({
        "service": "lacuene-exp",
        "tiers": {
            "curated": {"available": bool(_curated_sources), "genes": len(_curated_sources)},
            "expanded": {"available": bool(_expanded_genes), "genes": len(_expanded_genes)},
            "bulk": {"available": bool(_bulk_genes), "summary": _bulk_genes if _bulk_genes else None},
        }
    })


@app.route("/api/genes")
def genes():
    """List genes. Tier param selects data depth."""
    tier = request.args.get("tier", "curated")

    if tier == "curated":
        if not _curated_sources:
            return jsonify({"error": "Curated data not loaded", "hint": "Run: just generate"}), 503
        return jsonify({
            "tier": "curated",
            "count": len(_curated_sources),
            "genes": sorted(_curated_sources.keys()),
        })

    elif tier == "expanded":
        if not _expanded_genes:
            # Graceful degradation: fall back to curated
            if _curated_sources:
                return jsonify({
                    "tier": "curated",
                    "count": len(_curated_sources),
                    "genes": sorted(_curated_sources.keys()),
                    "_fallback": True,
                    "_reason": "Expanded data not available, serving curated",
                })
            return jsonify({"error": "No gene data available"}), 503

        return jsonify({
            "tier": "expanded",
            "count": len(_expanded_genes),
            "genes": [g["symbol"] for g in _expanded_genes],
        })

    elif tier == "genome":
        if not _bulk_genes:
            return jsonify({"error": "Bulk data not available", "hint": "Run: just bulk-craniofacial"}), 503
        return jsonify({
            "tier": "genome",
            "summary": _bulk_genes,
        })

    else:
        return jsonify({"error": f"Unknown tier: {tier}", "valid": ["curated", "expanded", "genome"]}), 400


@app.route("/api/genes/<symbol>")
def gene_detail(symbol: str):
    """Single gene detail from curated sources."""
    symbol = symbol.upper()

    if not _curated_sources:
        return jsonify({"error": "Curated data not loaded"}), 503

    if symbol not in _curated_sources:
        # Check if it's in expanded set
        expanded_match = next((g for g in _expanded_genes if g["symbol"] == symbol), None)
        if expanded_match:
            return jsonify({
                "symbol": symbol,
                "tier": "expanded",
                "hgnc": expanded_match,
                "curated_sources": None,
                "_note": "Gene is in expanded set but not yet curated. No source data available.",
            })
        abort(404, description=f"Gene {symbol} not found in any tier")

    return jsonify({
        "symbol": symbol,
        "tier": "curated",
        "sources": _curated_sources[symbol],
    })


@app.route("/api/gaps")
def gaps():
    """Research gap report."""
    if not _curated_gaps:
        return jsonify({"error": "Gap report not available", "hint": "Run: just generate"}), 503
    return jsonify(_curated_gaps)


@app.route("/api/coverage")
def coverage():
    """Source coverage matrix."""
    if not _curated_sources:
        return jsonify({"error": "No data"}), 503

    # Build coverage summary
    source_keys = [
        "go", "omim", "hpo", "uniprot", "facebase", "clinvar",
        "pubmed", "gnomad", "nih_reporter", "gtex", "clinicaltrials",
        "string", "orphanet", "opentargets", "models", "structures",
    ]

    coverage = {}
    for src in source_keys:
        flag = f"in_{src}"
        count = sum(1 for g in _curated_sources.values() if g.get(flag, False))
        coverage[src] = {
            "count": count,
            "total": len(_curated_sources),
            "percent": round(100 * count / len(_curated_sources), 1),
        }

    return jsonify({
        "total_genes": len(_curated_sources),
        "sources": coverage,
    })


@app.route("/")
def index():
    """API documentation."""
    return jsonify({
        "service": "lacuene-exp",
        "description": "Neural crest gene data API (curated + expanded tiers)",
        "endpoints": {
            "/api/status": "Health check with tier availability",
            "/api/genes": "List genes (tier=curated|expanded|genome)",
            "/api/genes/<symbol>": "Single gene detail",
            "/api/gaps": "Research gap report",
            "/api/coverage": "Source coverage matrix",
        },
    })


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    load_data()
    app.run(host=args.host, port=args.port, debug=True)
