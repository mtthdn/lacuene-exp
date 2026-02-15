#!/usr/bin/env python3
"""
Smoke tests for lacuene-exp API routes.

Uses Flask test client — no running server needed.
Tests route availability, response shapes, and graceful degradation.

Usage:
    python3 -m pytest tests/ -v
    python3 -m pytest tests/test_api.py -v
"""

import json
import math
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.serve import app, load_data


@pytest.fixture(scope="module")
def client():
    """Flask test client with data loaded."""
    app.config["TESTING"] = True
    load_data()
    with app.test_client() as c:
        yield c


# --- Route smoke tests ---

def test_index(client):
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["service"] == "lacuene-exp"
    assert "endpoints" in data
    assert "source" in data["endpoints"]
    assert "enrichment" in data["endpoints"]


def test_status(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "tiers" in data
    assert "curated" in data["tiers"]
    assert "expanded" in data["tiers"]
    assert isinstance(data["tiers"]["curated"]["genes"], int)


def test_genes_curated(client):
    resp = client.get("/api/genes")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["tier"] == "curated"
    assert isinstance(data["genes"], list)
    assert data["count"] == len(data["genes"])


def test_genes_expanded(client):
    resp = client.get("/api/genes?tier=expanded")
    assert resp.status_code == 200
    data = resp.get_json()
    # May fall back to curated if expanded data not available
    assert data["tier"] in ("expanded", "curated")
    assert isinstance(data["genes"], list)


def test_genes_invalid_tier(client):
    resp = client.get("/api/genes?tier=bogus")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_gene_detail_known(client):
    """Test gene detail for a known curated gene."""
    # Get the first curated gene
    genes_resp = client.get("/api/genes")
    genes = genes_resp.get_json().get("genes", [])
    if not genes:
        pytest.skip("No curated genes loaded")
    resp = client.get(f"/api/genes/{genes[0]}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["symbol"] == genes[0]
    assert "sources" in data or "hgnc" in data


def test_gene_detail_unknown(client):
    resp = client.get("/api/genes/ZZZZNOTREAL")
    assert resp.status_code == 404


def test_gene_detail_case_insensitive(client):
    """Symbols are uppercased by the route."""
    genes_resp = client.get("/api/genes")
    genes = genes_resp.get_json().get("genes", [])
    if not genes:
        pytest.skip("No curated genes loaded")
    resp = client.get(f"/api/genes/{genes[0].lower()}")
    assert resp.status_code == 200


def test_gaps(client):
    resp = client.get("/api/gaps")
    # May be 200 or 503 depending on data availability
    assert resp.status_code in (200, 503)


def test_coverage(client):
    resp = client.get("/api/coverage")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "sources" in data
    assert "total_genes" in data


def test_coverage_matrix(client):
    resp = client.get("/api/enrichment/coverage-matrix")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "matrix" in data
    assert "sources" in data
    assert isinstance(data["sources"], list)


def test_gap_candidates(client):
    resp = client.get("/api/enrichment/gap-candidates")
    # 200 if derived data exists, 503 otherwise
    assert resp.status_code in (200, 503)
    if resp.status_code == 200:
        data = resp.get_json()
        assert "candidates" in data
        assert data["tier"] == "derived"


def test_gap_candidates_filters(client):
    resp = client.get("/api/enrichment/gap-candidates?min_score=12&limit=5")
    if resp.status_code == 200:
        data = resp.get_json()
        assert len(data["candidates"]) <= 5
        for c in data["candidates"]:
            assert c["confidence_score"] >= 12


def test_provenance(client):
    resp = client.get("/api/enrichment/provenance")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "derivation_count" in data
    assert isinstance(data["derivations"], list)


def test_digest_json(client):
    resp = client.get("/api/digest")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "digest" in data
    assert "date" in data
    assert "## lacuene Digest" in data["digest"]


def test_digest_markdown(client):
    resp = client.get("/api/digest?format=md")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/markdown")
    text = resp.data.decode("utf-8")
    assert "## lacuene Digest" in text
    assert "Source Coverage" in text


# --- Scoring formula tests ---

class TestScoringFormula:
    """Test the gap candidate confidence scoring formula in isolation."""

    @staticmethod
    def score(hpo_count=0, orph_count=0, has_omim=False, omim_syndromes=0):
        """Replicate the scoring formula from derive_gap_candidates.py."""
        s = 0.0
        s += math.log2(hpo_count + 1) if hpo_count > 0 else 0
        s += math.log2(orph_count + 1) * 3 if orph_count > 0 else 0
        s += (2 + math.log2(omim_syndromes + 1)) if has_omim else 0
        return round(s, 1)

    def test_no_evidence(self):
        assert self.score() == 0

    def test_hpo_only(self):
        assert self.score(hpo_count=5) > 0
        # log2(6) ≈ 2.6
        assert abs(self.score(hpo_count=5) - 2.6) < 0.1

    def test_orphanet_only(self):
        # 1 disorder: log2(2) * 3 = 3.0
        assert self.score(orph_count=1) == 3.0

    def test_omim_base(self):
        # OMIM with 0 syndromes: 2 + log2(1) = 2 + 0 = 2.0
        assert self.score(has_omim=True, omim_syndromes=0) == 2.0

    def test_all_evidence(self):
        # HPO=100, Orphanet=5, OMIM with 3 syndromes
        s = self.score(hpo_count=100, orph_count=5, has_omim=True, omim_syndromes=3)
        # log2(101) + log2(6)*3 + 2 + log2(4) ≈ 6.66 + 7.75 + 2 + 2 = 18.4
        assert s > 15
        assert s < 25

    def test_score_monotonic_with_hpo(self):
        s1 = self.score(hpo_count=10)
        s2 = self.score(hpo_count=100)
        s3 = self.score(hpo_count=1000)
        assert s1 < s2 < s3

    def test_score_monotonic_with_orphanet(self):
        s1 = self.score(orph_count=1)
        s2 = self.score(orph_count=5)
        s3 = self.score(orph_count=20)
        assert s1 < s2 < s3

    def test_high_threshold(self):
        """Candidates with score >= 12 should have substantial evidence."""
        # Orphanet alone needs 15+ disorders: log2(16)*3 = 12.0
        assert self.score(orph_count=15) >= 12.0
        # HPO alone can't reach 12 easily — log2(4097) ≈ 12
        assert self.score(hpo_count=4096) >= 12.0

    def test_col2a1_approximate(self):
        """COL2A1 should score ~21 with HPO=360, Orphanet=18, OMIM=True."""
        s = self.score(hpo_count=360, orph_count=18, has_omim=True, omim_syndromes=5)
        assert 20 < s < 28
