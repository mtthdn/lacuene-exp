#!/usr/bin/env python3
"""
Benchmark CUE validation and export at various gene counts.

Generates synthetic CUE source files for N genes, then times:
  - cue vet (validation)
  - cue export -e gap_report (projection)
  - cue export -e gene_sources (sources)

Usage:
    python3 tests/benchmark_cue.py              # Default: 100, 250, 500
    python3 tests/benchmark_cue.py --genes 500  # Single target
"""

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = REPO_ROOT / "model"


def generate_gene_list_cue(symbols: list[str]) -> str:
    """Generate a gene_list.cue with N gene stubs."""
    lines = ['package lacuene\n', 'genes: {']
    for sym in symbols:
        lines.append(f'  "{sym}": #Gene & {{')
        lines.append(f'    symbol: "{sym}"')
        lines.append('  }')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def generate_source_cue(symbols: list[str], source_name: str,
                        flag: str, id_field: str) -> str:
    """Generate a minimal source CUE file that sets a flag for all genes."""
    lines = ['package lacuene\n', 'genes: {']
    for sym in symbols:
        lines.append(f'  "{sym}": {{')
        lines.append(f'    {flag}: true')
        if id_field:
            lines.append(f'    {id_field}: "FAKE_{sym}"')
        lines.append('  }')
    lines.append('}')
    return '\n'.join(lines) + '\n'


# Sources to simulate (flag, id_field)
SOURCES = {
    "go":              ("_in_go", "go_id"),
    "omim":            ("_in_omim", "omim_id"),
    "hpo":             ("_in_hpo", "hpo_gene_id"),
    "uniprot":         ("_in_uniprot", "uniprot_id"),
    "facebase":        ("_in_facebase", "facebase_id"),
    "clinvar":         ("_in_clinvar", "clinvar_gene_id"),
    "pubmed":          ("_in_pubmed", "pubmed_gene_id"),
    "gnomad":          ("_in_gnomad", "gnomad_id"),
    "gtex":            ("_in_gtex", "gtex_id"),
    "clinicaltrials":  ("_in_clinicaltrials", ""),
    "string":          ("_in_string", "string_id"),
    "orphanet":        ("_in_orphanet", "orphanet_id"),
    "opentargets":     ("_in_opentargets", "opentargets_id"),
    "models":          ("_in_models", ""),
    "structures":      ("_in_structures", ""),
    "nih_reporter":    ("_in_nih_reporter", ""),
}


def make_gene_symbols(n: int) -> list[str]:
    """Generate N fake gene symbols."""
    # Use real-ish looking symbols
    prefixes = ["BMP", "FGF", "SOX", "PAX", "WNT", "SHH", "TBX", "DLX",
                "MSX", "TWIST", "SNAI", "ZEB", "FOXD", "ALX", "ETS",
                "HAND", "TFAP", "EDN", "GJA", "COL", "MMP", "ADAM",
                "EPHB", "SEMA", "RUNX", "RARA", "IRF", "TP", "SMAD",
                "NOG", "CHRD", "TGFB"]
    symbols = []
    for i in range(n):
        prefix = prefixes[i % len(prefixes)]
        num = (i // len(prefixes)) + 1
        symbols.append(f"{prefix}{num}X")
    return symbols


def run_benchmark(n_genes: int) -> dict:
    """Run CUE benchmark with n_genes synthetic genes."""
    symbols = make_gene_symbols(n_genes)

    # Create temporary model directory with copies of real schema + projections
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Copy schema and projection files, skip source data (we generate our own)
        source_cue_names = {f"{s}.cue" for s in SOURCES}
        source_cue_names.add("nih_reporter.cue")  # also a source
        for f in MODEL_DIR.iterdir():
            if f.suffix != ".cue":
                continue
            if f.name == "gene_list.cue":
                continue  # we generate our own
            if f.name in source_cue_names:
                continue  # we generate synthetic versions
            shutil.copy(f, tmp / f.name)

        # Generate gene list
        gene_list = generate_gene_list_cue(symbols)
        (tmp / "gene_list.cue").write_text(gene_list)

        # Generate source files — only flag half the genes per source for realism
        import random
        random.seed(42)
        for source, (flag, id_field) in SOURCES.items():
            # Each source covers 30-80% of genes randomly
            coverage = random.uniform(0.3, 0.8)
            covered = random.sample(symbols, int(len(symbols) * coverage))
            source_cue = generate_source_cue(covered, source, flag, id_field)
            (tmp / f"{source}.cue").write_text(source_cue)

        # Measure file sizes
        total_lines = 0
        total_bytes = 0
        for f in tmp.iterdir():
            if f.suffix == ".cue":
                content = f.read_text()
                total_lines += content.count('\n')
                total_bytes += f.stat().st_size

        result = {
            "genes": n_genes,
            "cue_files": len(list(tmp.glob("*.cue"))),
            "total_lines": total_lines,
            "total_bytes": total_bytes,
        }

        # CUE requires relative paths — run from inside the temp dir
        cue_env = {"PATH": subprocess.os.environ.get("PATH", "")}

        # Benchmark: cue vet
        start = time.perf_counter()
        proc = subprocess.run(
            ["cue", "vet", "-c", "./"],
            capture_output=True, text=True, timeout=120,
            cwd=str(tmp)
        )
        vet_time = time.perf_counter() - start
        result["vet_seconds"] = round(vet_time, 3)
        result["vet_ok"] = proc.returncode == 0
        if proc.returncode != 0:
            result["vet_error"] = proc.stderr[:500]

        # Benchmark: cue export gap_report
        if result["vet_ok"]:
            start = time.perf_counter()
            proc = subprocess.run(
                ["cue", "export", "./", "-e", "gap_report"],
                capture_output=True, text=True, timeout=300,
                cwd=str(tmp)
            )
            export_time = time.perf_counter() - start
            result["export_gap_seconds"] = round(export_time, 3)
            result["export_gap_ok"] = proc.returncode == 0
            if proc.returncode == 0:
                result["export_gap_bytes"] = len(proc.stdout)
            else:
                result["export_gap_error"] = proc.stderr[:500]

            # Benchmark: cue export gene_sources
            start = time.perf_counter()
            proc = subprocess.run(
                ["cue", "export", "./", "-e", "gene_sources"],
                capture_output=True, text=True, timeout=300,
                cwd=str(tmp)
            )
            export_time = time.perf_counter() - start
            result["export_sources_seconds"] = round(export_time, 3)
            result["export_sources_ok"] = proc.returncode == 0

        return result


def main():
    parser = argparse.ArgumentParser(description="Benchmark CUE at scale")
    parser.add_argument("--genes", type=int, nargs="*",
                        default=[100, 250, 500],
                        help="Gene counts to benchmark")
    args = parser.parse_args()

    # First, baseline with real model
    print("Baseline: real model (82 genes)")
    start = time.perf_counter()
    proc = subprocess.run(
        ["cue", "vet", "-c", "./"],
        capture_output=True, text=True, timeout=60,
        cwd=str(MODEL_DIR)
    )
    baseline_vet = time.perf_counter() - start
    print(f"  cue vet: {baseline_vet:.3f}s (ok={proc.returncode == 0})")

    start = time.perf_counter()
    proc = subprocess.run(
        ["cue", "export", "./", "-e", "gap_report"],
        capture_output=True, text=True, timeout=60,
        cwd=str(MODEL_DIR)
    )
    baseline_export = time.perf_counter() - start
    print(f"  cue export gap_report: {baseline_export:.3f}s (ok={proc.returncode == 0})")
    print()

    results = []
    for n in args.genes:
        print(f"Benchmarking {n} genes...")
        result = run_benchmark(n)
        results.append(result)

        status = "OK" if result.get("vet_ok") else "FAIL"
        print(f"  Files: {result['cue_files']}, Lines: {result['total_lines']}, "
              f"Size: {result['total_bytes'] // 1024}KB")
        print(f"  cue vet:            {result['vet_seconds']}s [{status}]")
        if result.get("vet_ok"):
            print(f"  cue export gap:     {result.get('export_gap_seconds', 'N/A')}s")
            print(f"  cue export sources: {result.get('export_sources_seconds', 'N/A')}s")
        else:
            err = result.get("vet_error", "unknown")
            print(f"  Error: {err[:200]}")
        print()

    # Summary table
    print("=" * 70)
    print(f"{'Genes':>6} | {'Lines':>7} | {'Size':>7} | {'Vet':>8} | {'Export':>8} | Status")
    print("-" * 70)
    print(f"{'82':>6} | {'29000':>7} | {'~1MB':>7} | {baseline_vet:>7.3f}s | {baseline_export:>7.3f}s | baseline")
    for r in results:
        status = "OK" if r.get("vet_ok") else "FAIL"
        export = f"{r.get('export_gap_seconds', 0):>7.3f}s" if r.get("vet_ok") else "    N/A"
        print(f"{r['genes']:>6} | {r['total_lines']:>7} | "
              f"{r['total_bytes'] // 1024:>5}KB | {r['vet_seconds']:>7.3f}s | "
              f"{export} | {status}")
    print("=" * 70)

    # Save results
    out_path = REPO_ROOT / "output" / "bulk" / "cue_benchmark.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "baseline_82_genes": {
                "vet_seconds": round(baseline_vet, 3),
                "export_seconds": round(baseline_export, 3),
            },
            "benchmarks": results,
        }, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
