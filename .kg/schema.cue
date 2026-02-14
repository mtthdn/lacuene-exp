package kg

// Derivation audit record — tracks every derived dataset
#Derivation: {
	id:          string & =~"^DERIV_[0-9]{3}$"
	worker:      string   // script that produced this
	output_file: string   // path relative to derived/
	date:        string   // ISO 8601
	description: string

	// Canon purity tracking (finglonger pattern)
	canon_purity:      "pure" | "mixed" | "derived"
	canon_sources:     [...string]  // what source data was used
	non_canon_elements: [...string] // what was computed/inferred
	action_required:   string       // how to handle non-canon parts

	// Provenance
	input_files:  [...string]
	gene_count:   int
	record_count: int
}

// Insight — a discovery worth recording
#Insight: {
	id:         string & =~"^INSIGHT_[0-9]{3}$"
	statement:  string
	evidence:   [...string]  // file:line or data references
	method:     "cross_reference" | "gap_analysis" | "statistics" | "bulk_pipeline"
	confidence: "high" | "medium" | "low"
	discovered: string  // ISO 8601
	implication: string // what this means for research
	action_items: [...string]
}

// Rejected approach — prevent repeating failed work
#Rejected: {
	id:          string & =~"^REJ_[0-9]{3}$"
	approach:    string
	reason:      string
	date:        string
	alternative: string  // what to do instead
}
