package kg

REJ_001: #Rejected & {
	id:          "REJ_001"
	approach:    "Expand curated gene list in lacuene to 494 genes"
	reason:      "Pollutes curated pipeline with unverified genes. Researchers lose trust when they see COL25A1 in a neural crest tool without literature justification."
	date:        "2026-02-14"
	alternative: "Keep lacuene at 95 curated genes. Serve expanded set from lacuene-exp as a separate tier with canon purity metadata."
}

REJ_002: #Rejected & {
	id:          "REJ_002"
	approach:    "Include Zinc finger C2H2 genes in craniofacial expanded set"
	reason:      "760 ZNF genes overwhelm the set with noise. Most have no neural crest evidence. Gene group matching is too coarse for this family."
	date:        "2026-02-14"
	alternative: "Exclude entire ZNF C2H2 family. Consider individual ZNF genes only if they appear in HPO craniofacial phenotypes."
}

REJ_003: #Rejected & {
	id:          "REJ_003"
	approach:    "Run Flask API directly on Proxmox host (tulip)"
	reason:      "Proxmox host is infrastructure — running application services there violates isolation. A misbehaving Flask app could affect other VMs/containers."
	date:        "2026-02-14"
	alternative: "Deploy inside LXC container (638) with own IP, systemd service, and cron. Caddy (LXC 612) reverse-proxies to the container."
}
