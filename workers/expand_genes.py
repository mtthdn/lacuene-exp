#!/usr/bin/env python3
"""
Expand genes.py from 82 curated genes to ~500 craniofacial-adjacent genes.

Uses HGNC bulk data to add high-confidence genes from:
  - Gene groups: BMP, FGF, SOX, PAX, WNT, TBX, SMAD, cadherins, collagens, etc.
  - Name terms: cranio, facial, palate, cleft, etc.
  - Excludes: Zinc fingers C2H2-type (760 genes, too broad)

Cross-reference IDs (NCBI, UniProt, OMIM) come from HGNC data.
Developmental roles are auto-assigned from gene group membership.

Usage:
    python3 workers/expand_genes.py          # Preview
    python3 workers/expand_genes.py --write   # Write genes.py
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LACUENE_PATH = Path(os.environ.get("LACUENE_PATH", REPO_ROOT.parent / "lacuene"))
HGNC_FILE = REPO_ROOT / "expanded" / "hgnc_craniofacial.json"

# Map HGNC gene groups to developmental roles
GROUP_TO_ROLE = {
    # Signaling
    "Bone morphogenetic proteins": "signaling",
    "Fibroblast growth factors": "signaling",
    "Fibroblast growth factor receptors": "signaling",
    "Hedgehog signaling molecule": "signaling",
    "Wingless-type MMTV integration site family": "signaling",
    "WNT signaling pathway": "signaling",
    "Notch receptors": "signaling",
    "SMAD family": "signaling",
    "Transforming growth factor beta": "signaling",
    "Endothelin receptors": "signaling",
    "Retinoid receptors": "signaling",
    "Disintegrin and metallopeptidase domain": "signaling",

    # Transcription factors / patterning
    "Homeobox genes": "patterning",
    "Paired box genes": "border_spec",
    "SRY-boxes": "nc_specifier",
    "T-boxes": "patterning",
    "Forkhead boxes": "patterning",
    "Twist family": "nc_specifier",
    "Snail family": "nc_specifier",
    "Runt-related transcription factors": "patterning",

    # ECM / structural
    "Cadherins": "emt_migration",
    "Collagens": "structural",
    "Matrix metallopeptidases": "emt_migration",

    # Guidance / migration
    "Ephrin receptors": "emt_migration",
    "Semaphorins": "emt_migration",
    "Gap junction proteins": "structural",
}

# Name terms → developmental role
NAME_TERM_ROLES = {
    "cranio": "craniofacial",
    "facial": "craniofacial",
    "palate": "craniofacial",
    "cleft": "craniofacial",
    "dental": "craniofacial",
    "tooth": "craniofacial",
    "mandib": "craniofacial",
    "maxill": "craniofacial",
    "neural crest": "nc_specifier",
    "branchial": "craniofacial",
    "pharyngeal": "craniofacial",
    "otic": "craniofacial",
    "skeletal": "structural",
    "cartilage": "structural",
    "chondro": "structural",
    "osteo": "structural",
    "bone morpho": "signaling",
    "craniofacial": "craniofacial",
}


def load_hgnc_craniofacial() -> list[dict]:
    if not HGNC_FILE.exists():
        print(f"ERROR: {HGNC_FILE} not found. Run: python3 normalizers/bulk_hgnc.py --craniofacial",
              file=sys.stderr)
        sys.exit(1)
    with open(HGNC_FILE) as f:
        return json.load(f)


def assign_role(gene: dict) -> str:
    """Assign a developmental role based on source annotation."""
    source = gene.get("source", "")

    if source == "curated":
        return ""  # Keep existing role from current genes.py

    if source.startswith("group:"):
        group_name = source.replace("group:", "")
        for pattern, role in GROUP_TO_ROLE.items():
            if pattern.lower() in group_name.lower():
                return role
        return "other"

    if source.startswith("name:"):
        term = source.replace("name:", "")
        return NAME_TERM_ROLES.get(term, "craniofacial")

    return "other"


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write expanded genes.py")
    parser.add_argument("--exclude-znf", action="store_true", default=True,
                        help="Exclude Zinc fingers C2H2-type (default: True)")
    args = parser.parse_args()

    # Load current curated genes
    sys.path.insert(0, str(LACUENE_PATH / "normalizers"))
    from genes import GENES as curated_genes, ROLES as curated_roles

    # Load HGNC craniofacial genes
    hgnc_genes = load_hgnc_craniofacial()

    # Filter out ZNF
    if args.exclude_znf:
        before = len(hgnc_genes)
        hgnc_genes = [g for g in hgnc_genes
                       if "Zinc fingers C2H2" not in str(g.get("source", ""))]
        print(f"Excluded ZNF: {before} -> {len(hgnc_genes)} genes")

    # Build expanded gene dict
    expanded = {}
    roles_expanded = {}

    # First: all curated genes (preserve exact IDs and roles)
    for sym, ids in curated_genes.items():
        expanded[sym] = ids

    # Build reverse role lookup from curated
    curated_role_lookup = {}
    for role, symbols in curated_roles.items():
        for s in symbols:
            curated_role_lookup[s] = role

    # Add new genes from HGNC
    new_count = 0
    for gene in sorted(hgnc_genes, key=lambda g: g["symbol"]):
        sym = gene["symbol"]
        if sym in expanded:
            continue  # Already curated

        # Build cross-reference dict
        ids = {
            "ncbi": gene.get("ncbi_id", ""),
            "uniprot": gene.get("uniprot_id", ""),
            "omim": gene.get("omim_id", ""),
        }

        # Skip genes with no NCBI ID (normalizers need it)
        if not ids["ncbi"]:
            continue

        expanded[sym] = ids
        new_count += 1

        # Assign role
        role = assign_role(gene)
        if role:
            if role not in roles_expanded:
                roles_expanded[role] = []
            roles_expanded[role].append(sym)

    print(f"\nExpansion: {len(curated_genes)} curated + {new_count} new = {len(expanded)} total")

    # Merge roles
    final_roles = {}
    for role, symbols in curated_roles.items():
        final_roles[role] = list(symbols)  # copy

    for role, symbols in roles_expanded.items():
        if role not in final_roles:
            final_roles[role] = []
        final_roles[role].extend(symbols)

    # Print role summary
    print("\nRoles:")
    for role, symbols in sorted(final_roles.items()):
        print(f"  {role}: {len(symbols)}")

    if not args.write:
        print("\nDry run. Use --write to update genes.py")
        return

    # Generate genes.py
    output = REPO_ROOT / "normalizers" / "genes.py"
    lines = []
    lines.append('#!/usr/bin/env python3')
    lines.append('"""')
    lines.append('Canonical gene list and cross-reference IDs for neural crest genes.')
    lines.append('')
    lines.append('This is the name resolution layer. Every normalizer imports GENES to know')
    lines.append('which genes to query and how to map source-native IDs back to HGNC symbols.')
    lines.append('')
    lines.append(f'Contains {len(expanded)} craniofacial-adjacent genes across {len(final_roles)} developmental roles.')
    lines.append('')
    lines.append('Core curated set (82 genes): hand-verified from neural crest GRN literature.')
    lines.append(f'Expanded set ({new_count} genes): auto-populated from HGNC gene groups and name terms.')
    lines.append('')
    lines.append('References:')
    lines.append('  Simoes-Costa & Bronner, Development 142:242-257 (2015)')
    lines.append('  Martik & Bronner, Nat Rev Mol Cell Biol 18:453-464 (2017)')
    lines.append('  Sauka-Spengler & Bronner-Fraser, Nat Rev Mol Cell Biol 9:557-568 (2008)')
    lines.append('"""')
    lines.append('')
    lines.append('# Each entry: HGNC symbol -> known IDs across sources.')
    lines.append('# ncbi   = NCBI Gene ID (human)')
    lines.append('# uniprot = UniProt canonical accession (human)')
    lines.append('# omim   = OMIM gene/locus MIM number')
    lines.append('GENES = {')

    # Write curated genes first, with original role headers
    role_order = ["border_spec", "nc_specifier", "emt_migration", "signaling",
                  "craniofacial", "melanocyte", "enteric", "cardiac"]

    role_headers = {
        "border_spec": "Neural plate border specification",
        "nc_specifier": "Neural crest specifiers",
        "emt_migration": "EMT and migration",
        "signaling": "Signaling pathways",
        "craniofacial": "Craniofacial patterning and disease",
        "melanocyte": "Melanocyte / pigmentation",
        "enteric": "Enteric nervous system",
        "cardiac": "Cardiac neural crest",
    }

    # Write curated genes by role
    for role in role_order:
        header = role_headers.get(role, role)
        lines.append(f'    # -- {header} (curated) {"─" * max(1, 52 - len(header))}')
        for sym in sorted(curated_roles[role]):
            ids = curated_genes[sym]
            ncbi = ids["ncbi"]
            uni = ids["uniprot"]
            omim = ids["omim"]
            pad = " " * max(1, 9 - len(sym))
            lines.append(f'    "{sym}":{pad}{{"ncbi": "{ncbi}",{" " * max(1, 8 - len(ncbi))}'
                        f'"uniprot": "{uni}", "omim": "{omim}"}},')
        lines.append('')

    # Write expanded genes by role
    expanded_role_order = ["signaling", "patterning", "nc_specifier", "border_spec",
                           "emt_migration", "structural", "craniofacial", "other"]

    expanded_role_headers = {
        "signaling": "Signaling (HGNC gene groups)",
        "patterning": "Patterning / transcription factors (HGNC)",
        "nc_specifier": "Neural crest specifiers (HGNC)",
        "border_spec": "Border specification (HGNC)",
        "emt_migration": "EMT and migration (HGNC)",
        "structural": "Structural / ECM (HGNC)",
        "craniofacial": "Craniofacial (name term match)",
        "other": "Other craniofacial-adjacent (HGNC)",
    }

    for role in expanded_role_order:
        symbols = roles_expanded.get(role, [])
        if not symbols:
            continue
        header = expanded_role_headers.get(role, role)
        lines.append(f'    # -- {header} {"─" * max(1, 52 - len(header))}')
        for sym in sorted(symbols):
            ids = expanded[sym]
            ncbi = ids["ncbi"]
            uni = ids["uniprot"]
            omim = ids["omim"]
            pad = " " * max(1, 9 - len(sym))
            lines.append(f'    "{sym}":{pad}{{"ncbi": "{ncbi}",{" " * max(1, 8 - len(ncbi))}'
                        f'"uniprot": "{uni}", "omim": "{omim}"}},')
        lines.append('')

    lines.append('}')
    lines.append('')

    # Write ROLES dict
    lines.append('# Developmental role classification (for VizData coloring)')
    lines.append('ROLES = {')

    all_roles = {}
    for role in role_order:
        all_roles[role] = sorted(curated_roles[role])
    for role in expanded_role_order:
        symbols = roles_expanded.get(role, [])
        if symbols:
            if role not in all_roles:
                all_roles[role] = []
            all_roles[role].extend(sorted(symbols))

    for role in list(role_order) + [r for r in expanded_role_order if r not in role_order]:
        if role not in all_roles or not all_roles[role]:
            continue
        syms = all_roles[role]
        lines.append(f'    "{role}": [')
        # Write in groups of 5
        for i in range(0, len(syms), 5):
            chunk = syms[i:i+5]
            formatted = ", ".join(f'"{s}"' for s in chunk)
            lines.append(f'        {formatted},')
        lines.append('    ],')

    lines.append('}')
    lines.append('')

    # Utility code
    lines.append('SYMBOL_TO_ROLE = {}')
    lines.append('for role, symbols in ROLES.items():')
    lines.append('    for s in symbols:')
    lines.append('        SYMBOL_TO_ROLE[s] = role')
    lines.append('')
    lines.append('# Reverse lookups')
    lines.append('NCBI_TO_SYMBOL = {v["ncbi"]: k for k, v in GENES.items()}')
    lines.append('UNIPROT_TO_SYMBOL = {v["uniprot"]: k for k, v in GENES.items()}')
    lines.append('OMIM_TO_SYMBOL = {v["omim"]: k for k, v in GENES.items()}')
    lines.append('')
    lines.append('')
    lines.append('def gene_symbols() -> list[str]:')
    lines.append('    """Return sorted list of all gene symbols."""')
    lines.append('    return sorted(GENES.keys())')
    lines.append('')
    lines.append('')
    lines.append('def export_cue(output_path: str):')
    lines.append('    """Export gene list as CUE for model self-description."""')
    lines.append('    lines = [')
    lines.append('        "package lacuene",')
    lines.append('        "",')
    lines.append('        "// Canonical gene list with HGNC symbols.",')
    lines.append('        "// Auto-generated from normalizers/genes.py -- do not hand-edit.",')
    lines.append('        f"// {len(GENES)} genes across {len(ROLES)} developmental roles.",')
    lines.append('        "",')
    lines.append('    ]')
    lines.append('    for symbol in sorted(GENES.keys()):')
    lines.append("        lines.append(f'genes: \"{symbol}\": symbol: \"{symbol}\"')")
    lines.append('    lines.append("")')
    lines.append('    with open(output_path, "w") as f:')
    lines.append('        f.write("\\n".join(lines))')
    lines.append('    print(f"Exported {len(GENES)} genes to {output_path}")')
    lines.append('')
    lines.append('')
    lines.append('if __name__ == "__main__":')
    lines.append('    import os')
    lines.append('    output = os.path.join(os.path.dirname(__file__), "..", "model", "gene_list.cue")')
    lines.append('    export_cue(output)')
    lines.append('')

    with open(output, "w") as f:
        f.write('\n'.join(lines))

    print(f"\nWrote {len(expanded)} genes to {output}")
    print("Run: python3 normalizers/genes.py  # to regenerate gene_list.cue")


if __name__ == "__main__":
    main()
