package kg

INSIGHT_001: #Insight & {
	id:         "INSIGHT_001"
	statement:  "CUE scales linearly with gene count at ~0.5ms/gene for validation and export"
	evidence:   ["workers/benchmark_cue.py", "500 genes: 0.24s, 1000: 0.56s, 5000: 2.9s"]
	method:     "statistics"
	confidence: "high"
	discovered: "2026-02-14"
	implication: "CUE can handle the full 494-gene expanded set without architectural changes"
	action_items: ["No need for Python-only pipeline below ~5000 genes"]
}

INSIGHT_002: #Insight & {
	id:         "INSIGHT_002"
	statement:  "760 of 1254 craniofacial-adjacent HGNC genes are Zinc finger C2H2 family — too broad for neural crest relevance"
	evidence:   ["workers/bulk_hgnc.py gene group analysis", "ZNF genes lack neural crest literature support"]
	method:     "cross_reference"
	confidence: "high"
	discovered: "2026-02-14"
	implication: "Gene group matching alone is insufficient — ZNF exclusion is mandatory for usable expanded set"
	action_items: ["Always filter ZNF from expanded tier", "Consider per-family relevance scoring"]
}

INSIGHT_003: #Insight & {
	id:         "INSIGHT_003"
	statement:  "94 genes have 5+ HPO phenotypes but are not in the curated 95-gene set — potential research candidates"
	evidence:   ["workers/bulk_downloads.py --craniofacial output", "genome_wide_summary.json"]
	method:     "gap_analysis"
	confidence: "medium"
	discovered: "2026-02-14"
	implication: "Bulk pipeline identifies discovery candidates that merit individual literature review"
	action_items: ["Build gap_candidates derivation worker", "Surface via /api/enrichment/gap-candidates"]
}
