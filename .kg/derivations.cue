package kg

DERIV_001: #Derivation & {
	id:          "DERIV_001"
	worker:      "workers/bulk_hgnc.py"
	output_file: "expanded/hgnc_craniofacial.json"
	date:        "2026-02-14"
	description: "HGNC protein-coding gene set filtered to craniofacial-adjacent genes"

	canon_purity:      "mixed"
	canon_sources:     ["HGNC complete gene set (19,296 protein-coding)"]
	non_canon_elements: ["Gene group matching heuristic", "Name term matching heuristic", "ZNF exclusion rule"]
	action_required:   "Individual gene relevance not verified — use as discovery candidates, not assertions"

	input_files: ["data/hgnc/hgnc_complete.json"]
	gene_count:   494
	record_count: 494
}

DERIV_002: #Derivation & {
	id:          "DERIV_002"
	worker:      "workers/bulk_downloads.py"
	output_file: "derived/genome_wide.csv"
	date:        "2026-02-14"
	description: "Genome-wide cross-reference of HGNC genes against HPO, Orphanet, OMIM bulk data"

	canon_purity:      "derived"
	canon_sources:     ["HGNC", "HPO annotations", "Orphanet gene-disease", "OMIM morbidmap"]
	non_canon_elements: ["Cross-reference join logic", "Phenotype count thresholds"]
	action_required:   "Bulk pipeline only — no per-gene API validation performed"

	input_files: ["expanded/hgnc_craniofacial.json"]
	gene_count:   1254
	record_count: 1254
}

DERIV_003: #Derivation & {
	id:          "DERIV_003"
	worker:      "workers/derive_gap_candidates.py"
	output_file: "derived/gap_candidates.json"
	date:        "2026-02-14"
	description: "Genes with disease signal (HPO/Orphanet/OMIM) not in curated 95-gene set — research candidates"

	canon_purity:      "derived"
	canon_sources:     ["HGNC", "HPO annotations", "Orphanet gene-disease", "OMIM morbidmap"]
	non_canon_elements: ["Confidence scoring formula (HPO count + Orphanet + OMIM)", "ZNF exclusion rule", "Ranking heuristic"]
	action_required:   "Candidates require individual literature review before promotion to curated set"

	input_files: ["expanded/hgnc_craniofacial.json", "derived/genome_wide.csv"]
	gene_count:   154
	record_count: 154
}
