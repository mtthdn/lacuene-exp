# The Reconciliation Pattern: One Architecture, Three Domains

## The Problem That Won't Go Away

Every organization has the same problem: multiple systems describing the same
things in different ways, and no single source of truth that's actually true.

A gene appears in 16 biomedical databases with different identifiers, different
fields, and different coverage gaps. A virtual machine appears in vCenter, TopDesk,
and your dependency graph with conflicting IPs and names. A Futurama character
appears in episode transcripts, game definitions, and AI-generated dialogue trees
with varying levels of canon fidelity.

The standard approaches — ETL pipelines, master data management, data lakes —
solve this by picking a winner and flattening everything else. But when your sources
are authoritative in *different ways* (vCenter knows the real IP, TopDesk knows the
asset owner, your monitoring system knows if it's actually alive), flattening
destroys information.

We built the same system three times, for three completely different domains,
and the architecture didn't change.

## The Pattern

```
Sources → Normalizers → CUE Unification → Projections → API / UI
                              ↓
                     Overnight Workers → Derived Insights
                              ↓
                     Knowledge Graph (.kg/)
```

Five principles make it work:

### 1. Sources OBSERVE, Resolutions DECIDE

Each source gets its own namespaced fields. No source overwrites another.

In **lacuene** (biomedical gene reconciliation), each source owns its claims:
```cue
// GO source writes go_id, _in_go
// OMIM source writes omim_id, _in_omim
// They never collide — the schema namespaces them
genes: "IRF6": {
    go_id:    "GO:0003700"
    omim_id:  "607199"
    _in_go:   true
    _in_omim: true
}
```

In **the datacenter** (VM reconciliation at UOttawa), the same pattern:
```cue
vms: "webserver-01": {
    vcenter_ip:    "10.0.1.50"     // vCenter says this
    topdesk_ip:    "10.0.1.51"     // TopDesk says that
    infragraph_ip: "10.0.1.50"     // infra-graph agrees with vCenter
    _in_vcenter:    true
    _in_topdesk:    true
    _in_infragraph: true
}
```

In **finglonger** (Futurama MUD game data), the corpus and derived layers:
```
actions/drink_slurm:
    transcript_source: "S01E01"      // Canon: from episode transcript
    game_effect: "+5 energy"         // Derived: game design layer
    embedding: [0.12, -0.34, ...]    // Computed: overnight worker
```

### 2. CUE as a Lattice, Not a Database

CUE's unification semantics mean you don't write merge logic. You write facts,
and CUE constructs the unified view through lattice joins. If two sources agree,
they unify. If they conflict, CUE reports `_|_` (bottom) — which is itself
useful information (it means you found a data quality issue).

This is fundamentally different from SQL joins or ETL merges:
- **SQL**: You write the join logic. If you get it wrong, silent data loss.
- **ETL**: You pick a winner. The losers' data is gone.
- **CUE**: You state facts. The lattice does the math. Conflicts surface automatically.

### 3. Tiered Data with Canon Purity

Not all data has the same provenance. We track this explicitly:

| Purity | Meaning | Example |
|--------|---------|---------|
| **pure** | Verified by authoritative source or literature | lacuene's 95 curated genes, datacenter's vCenter data |
| **mixed** | Algorithmically selected, partially verified | lacuene's 494 expanded genes (HGNC gene group matching) |
| **derived** | Computed from other tiers | Gap candidates, embeddings, similarity scores |

Every derived dataset carries `_provenance` metadata:
```json
{
  "_provenance": {
    "worker": "derive_gap_candidates.py",
    "canon_purity": "derived",
    "canon_sources": ["HGNC", "HPO"],
    "non_canon_elements": ["Confidence scoring formula"]
  }
}
```

Finglonger calls this the "canon purity audit" — every NPC dialogue, every
insult corpus entry, every action similarity score is tagged with where it came
from and what was computed vs extracted.

### 4. Curated Core, Derived Periphery

The curated pipeline stays small and trusted. The experimental/derived layer
lives in a separate repo with its own lifecycle.

| Project | Curated Core | Derived Layer |
|---------|-------------|---------------|
| lacuene | 95 genes, CUE model, 16 API sources | lacuene-exp: 494 expanded genes, gap candidates |
| finglonger | 111 episode transcripts, hand-verified | finglonger-overnight: 226MB of embeddings, similarities |
| datacenter | vCenter export (ground truth) | Projections: IP conflicts, SPOF detection, capacity |

The API separates these clearly. Source routes serve curated data unchanged.
Enrichment routes serve derived data with provenance. If the overnight pipeline
hasn't run, enrichment returns 503 and the source routes keep working.

### 5. Overnight Workers, Not Real-Time Pipelines

Derived data is computed in batch, not streamed. This is intentional:

- **Idempotent**: Workers check for existing output and skip if fresh
- **Phased**: GPU phases (embeddings) can be skipped if hardware unavailable
- **Auditable**: Every run logs to `overnight_YYYYMMDD.log`
- **Recoverable**: If phase 3 fails, phases 1-2 outputs are still usable

Finglonger runs 52 workers nightly at 1 AM. lacuene-exp runs 3 workers weekly.
The datacenter runs normalizers on-demand after vCenter exports. Same pattern,
different cadence.

## What Makes It Universal

The three domains share zero subject matter:

| | lacuene | datacenter | finglonger |
|---|---------|-----------|------------|
| **Domain** | Biomedical genetics | IT infrastructure | Game design |
| **Entities** | Genes | Virtual machines | Characters, items, actions |
| **Sources** | 16 APIs + bulk files | 4 enterprise systems | Episode transcripts + AI |
| **Scale** | 95 curated + 1,254 bulk | 1,178 VMs from 3 sources | 9,490 actions, 122 episodes |
| **Output** | Static site + REST API | Conflict report + graph | WebSocket MUD + REST API |

But the architecture is identical:

1. **Per-source normalizers** write namespaced fields into a shared schema
2. **CUE unification** constructs the reconciled model (no merge code)
3. **Projections** extract analytical views (gaps, conflicts, anomalies)
4. **Derived workers** compute insights the projections can't express
5. **API** serves both tiers with provenance metadata
6. **Knowledge graph** tracks what was learned and what was tried

## The Payoff

When you add a 17th data source to lacuene, you:
1. Write a normalizer (Python script, ~100 lines)
2. Add the source's fields to `schema.cue` (5 lines)
3. Run `cue vet` — it tells you if anything conflicts

That's it. No ETL pipeline to update. No join logic to debug. No migration script.
The new source's data unifies with everything else automatically.

When the datacenter team adds Zabbix monitoring data alongside vCenter and TopDesk,
the same pattern applies. When finglonger adds a new AI enrichment pass, it layers
on top of the existing canon without touching it.

The pattern works because it separates three concerns that other architectures
conflate:

- **Observation** (what each source claims) — handled by normalizers
- **Unification** (what the combined model looks like) — handled by CUE
- **Decision** (what to do about conflicts) — handled by projections and humans

Most data integration systems try to do all three in the same step, which is
why they break every time a source changes. This architecture lets each concern
evolve independently.

## Try It

The simplest version is three files:

```cue
// schema.cue — define your entity
#Thing: {
    name: string
    _in_source_a: *false | true
    _in_source_b: *false | true
    source_a_value?: string
    source_b_value?: string
}
things: [string]: #Thing

// source_a.cue — normalizer output
things: "item1": { _in_source_a: true, source_a_value: "hello" }

// source_b.cue — normalizer output
things: "item1": { _in_source_b: true, source_b_value: "world" }
```

Run `cue vet -c ./` and you have a unified model. Add projections for gap
analysis. Add an overnight worker for enrichment. Add an API with two tiers.
Scale from there.

The domain doesn't matter. The sources don't matter. The pattern works.
