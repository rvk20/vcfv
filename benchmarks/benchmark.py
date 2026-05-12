"""
Benchmark: vcfv vs scikit-allel vs pandas

Runs each tool N times, drops the top and bottom 10% of timings
(trimmed mean), and reports mean, median, stdev, and peak RAM.

Usage:
    python benchmarks/benchmark.py path/to/your.vcf [--runs 10]

Requirements:
    pip install vcfv[benchmark]
    # or: pip install scikit-allel psutil
"""
import sys
import json
import math
import argparse
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Worker scripts (run in isolated subprocesses)
# ---------------------------------------------------------------------------

WORKER_VCFV_FULL_EAGER = """
import json, time, os, psutil
from vcfv import read_vcf
path = {path!r}
proc = psutil.Process(os.getpid())
mem_before = proc.memory_info().rss
t0 = time.perf_counter()
df = read_vcf(path, parse_info="wide", parse_format="wide")
elapsed = time.perf_counter() - t0
mem_after = proc.memory_info().rss
print(json.dumps({{"elapsed": elapsed, "ram_mb": (mem_after - mem_before) / 1024 / 1024, "rows": len(df)}}))
"""

WORKER_VCFV_FULL_LAZY = """
import json, time, os, psutil
from vcfv import read_vcf
path = {path!r}
proc = psutil.Process(os.getpid())
mem_before = proc.memory_info().rss
t0 = time.perf_counter()
df = read_vcf(path, parse_info="wide", parse_format="wide", lazy=True).collect()
elapsed = time.perf_counter() - t0
mem_after = proc.memory_info().rss
print(json.dumps({{"elapsed": elapsed, "ram_mb": (mem_after - mem_before) / 1024 / 1024, "rows": len(df)}}))
"""

WORKER_VCFV_FULL_INFER_ALL = """
import json, time, os, psutil
from vcfv import read_vcf
path = {path!r}
proc = psutil.Process(os.getpid())
mem_before = proc.memory_info().rss
t0 = time.perf_counter()
df = read_vcf(path, parse_info="wide", parse_format="wide", infer_info_keys_from="all", infer_format_keys_from="all")
elapsed = time.perf_counter() - t0
mem_after = proc.memory_info().rss
print(json.dumps({{"elapsed": elapsed, "ram_mb": (mem_after - mem_before) / 1024 / 1024, "rows": len(df)}}))
"""

WORKER_VCFV_RAW_EAGER = """
import json, time, os, psutil
from vcfv import read_vcf
path = {path!r}
proc = psutil.Process(os.getpid())
mem_before = proc.memory_info().rss
t0 = time.perf_counter()
df = read_vcf(path, parse_info=False, parse_format=False)
elapsed = time.perf_counter() - t0
mem_after = proc.memory_info().rss
print(json.dumps({{"elapsed": elapsed, "ram_mb": (mem_after - mem_before) / 1024 / 1024, "rows": len(df)}}))
"""

WORKER_VCFV_RAW_LAZY = """
import json, time, os, psutil
from vcfv import read_vcf
path = {path!r}
proc = psutil.Process(os.getpid())
mem_before = proc.memory_info().rss
t0 = time.perf_counter()
df = read_vcf(path, parse_info=False, parse_format=False, lazy=True).collect()
elapsed = time.perf_counter() - t0
mem_after = proc.memory_info().rss
print(json.dumps({{"elapsed": elapsed, "ram_mb": (mem_after - mem_before) / 1024 / 1024, "rows": len(df)}}))
"""

WORKER_SCIKIT = """
import json, time, os, psutil
import allel
path = {path!r}
proc = psutil.Process(os.getpid())
mem_before = proc.memory_info().rss
t0 = time.perf_counter()
df = allel.vcf_to_dataframe(path)
elapsed = time.perf_counter() - t0
mem_after = proc.memory_info().rss
print(json.dumps({{"elapsed": elapsed, "ram_mb": (mem_after - mem_before) / 1024 / 1024, "rows": len(df)}}))
"""

WORKER_PANDAS = """
import json, time, os, psutil
import pandas as pd
path = {path!r}
proc = psutil.Process(os.getpid())
skip = 0
with open(path) as f:
    for line in f:
        if line.startswith("##"):
            skip += 1
        else:
            break
mem_before = proc.memory_info().rss
t0 = time.perf_counter()
df = pd.read_csv(path, sep="\\t", skiprows=skip)
elapsed = time.perf_counter() - t0
mem_after = proc.memory_info().rss
print(json.dumps({{"elapsed": elapsed, "ram_mb": (mem_after - mem_before) / 1024 / 1024, "rows": len(df)}}))
"""


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def trimmed_mean(values: list[float], trim: float = 0.1) -> float:
    n = len(values)
    cut = max(1, math.floor(n * trim))
    trimmed = sorted(values)[cut:-cut] if cut > 0 else values
    return sum(trimmed) / len(trimmed)


def median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return (s[mid - 1] + s[mid]) / 2 if n % 2 == 0 else s[mid]


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_once(script: str, path: str) -> dict:
    code = script.format(path=path)
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip().splitlines()[-1]}
        last_line = result.stdout.strip().splitlines()[-1]
        return json.loads(last_line)
    except subprocess.TimeoutExpired:
        return {"error": "timeout (>300s)"}
    except Exception as e:
        return {"error": str(e)}


def run_tool(label: str, script: str, path: str, runs: int) -> dict:
    timings = []
    ram_samples = []
    rows = 0
    error = None

    for i in range(runs):
        print(f"  {label:<50} run {i + 1}/{runs}...", end="\r")
        result = run_once(script, path)

        if "error" in result:
            error = result["error"]
            break

        timings.append(result["elapsed"])
        ram_samples.append(result["ram_mb"])
        rows = result["rows"]

    print(" " * 75, end="\r")

    if error:
        return {"label": label, "error": error}

    return {
        "label":  label,
        "mean":   trimmed_mean(timings),
        "median": median(timings),
        "stdev":  stdev(timings),
        "ram_mb": trimmed_mean(ram_samples),
        "rows":   rows,
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def print_section(title: str) -> None:
    print(f"\n  {title}")
    print(f"  {'Tool':<50} {'mean':>6}  {'median':>6}  {'stdev':>6}  {'RAM':>8}  {'Rows':>10}")
    print("  " + "-" * 96)


def print_row(r: dict) -> None:
    if "error" in r:
        print(f"  {r['label']:<50} ERROR: {r['error']}")
    else:
        print(
            f"  {r['label']:<50}"
            f" {r['mean']:5.2f}s"
            f"  {r['median']:5.2f}s"
            f"  ±{r['stdev']:4.2f}s"
            f"  {r['ram_mb']:7.1f} MB"
            f"  {r['rows']:>10,}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="vcfv benchmark")
    parser.add_argument("vcf", help="Path to VCF file")
    parser.add_argument("--runs", type=int, default=10, help="Number of runs per tool (default: 10)")
    args = parser.parse_args()

    path = args.vcf
    runs = args.runs

    if not Path(path).exists():
        print(f"File not found: {path}")
        sys.exit(1)

    with open(path) as f:
        total = sum(1 for line in f if not line.startswith("#"))

    print(f"\nBenchmark: {path}")
    print(f"Variants:  {total:,}")
    print(f"Runs:      {runs} (trimmed mean: top/bottom 10% dropped)")
    print(f"RAM:       psutil RSS delta per subprocess")

    vcfv_tools = [
        ("vcfv eager  (INFO+FORMAT expanded, header)", WORKER_VCFV_FULL_EAGER),
        ("vcfv lazy   (INFO+FORMAT expanded, header)", WORKER_VCFV_FULL_LAZY),
        ("vcfv eager  (INFO+FORMAT expanded, all)",    WORKER_VCFV_FULL_INFER_ALL),
        ("vcfv eager  (no expansion)",                 WORKER_VCFV_RAW_EAGER),
        ("vcfv lazy   (no expansion)",                 WORKER_VCFV_RAW_LAZY),
    ]

    baseline_tools = [
        ("scikit-allel (no expansion)",           WORKER_SCIKIT),
        ("pandas raw TSV (no expansion)",         WORKER_PANDAS),
    ]

    print_section("vcfv")
    for label, worker in vcfv_tools:
        print_row(run_tool(label, worker, path, runs))

    print_section("Baselines (apples-to-apples: no INFO/FORMAT expansion)")
    for label, worker in baseline_tools:
        print_row(run_tool(label, worker, path, runs))

    print("\n  " + "-" * 96)
    print("\nNotes:")
    print("  - 'header' = INFO/FORMAT keys taken from ##INFO/##FORMAT header lines (default, fastest).")
    print("  - 'all'    = keys discovered by streaming entire file — safe for incomplete headers.")
    print("  - scikit-allel and pandas keep INFO and FORMAT as raw strings.")
    print("  - Compare 'vcfv (no expansion)' vs baselines for fair speed comparison.")
    print("  - stdev shows run-to-run variance; lower = more stable timing.")
    print("  - RAM = RSS delta measured per subprocess (includes Rust/C heap).")
    print()


if __name__ == "__main__":
    main()