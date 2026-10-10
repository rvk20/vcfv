## What's new in 0.3.0
- `.vcf.gz` files are now streamed lazily without loading into memory

# vcfv

Fast VCF parser to Polars/Pandas DataFrame with INFO and FORMAT field expansion.

```python
from vcfv import read_vcf

df = read_vcf("variants.vcf", parse_info="wide", parse_format="wide")
```

## Why vcfv?

Existing VCF parsers either load the entire file into memory at once, keep INFO and FORMAT as raw strings, or are built on aging dependencies. `vcfv` is built on [Polars](https://pola.rs) which gives you:

- **Lazy evaluation** — filters and projections are pushed down before reading
- **Native INFO and FORMAT expansion** — split into typed DataFrame columns in a single call
- **Simple API** — one function, sensible defaults
- **Gzip support** — reads `.vcf.gz` transparently

## Installation

```bash
pip install vcfv
```

With Pandas support:

```bash
pip install vcfv[pandas]
```

## Usage

### Basic

```python
from vcfv import read_vcf

# Returns a Polars DataFrame
df = read_vcf("variants.vcf")
```

### INFO and FORMAT expansion

```python
# Expand INFO fields into typed columns (INFO_AC, INFO_AF, INFO_DP, ...)
df = read_vcf("variants.vcf", parse_info="wide")

# Expand FORMAT fields per sample (Sample1_GT, Sample1_DP, ...)
df = read_vcf("variants.vcf", parse_format="wide")

# Both at once
df = read_vcf("variants.vcf", parse_info="wide", parse_format="wide")
```

### Lazy evaluation

```python
import polars as pl
from vcfv import read_vcf

# Returns a LazyFrame — nothing is read until .collect()
lf = read_vcf("variants.vcf", lazy=True)

# Combine with any Polars lazy operations before collecting
df = lf.filter(pl.col("CHROM") == "chr1").collect()
```

### Filtering

```python
# Filter by minimum QUAL score — rows with QUAL=. are excluded
df = read_vcf("variants.vcf", min_qual=30.0)

# Filter by genomic region — format: "chrom:start-end"
df = read_vcf("variants.vcf", region="chr1:1000000-2000000")

# Select specific output columns
df = read_vcf("variants.vcf", fields=["CHROM", "POS", "REF", "ALT"])

# Combine filters freely
df = read_vcf(
    "variants.vcf",
    parse_info="wide",
    parse_format="wide",
    min_qual=30.0,
    region="chr1:1000000-2000000",
    fields=["CHROM", "POS", "REF", "ALT", "INFO_AF"],
)
```

### Gzip support

```python
df = read_vcf("variants.vcf.gz")
```

### Chunked iteration for large files

```python
from vcfv import iter_vcf

for chunk in iter_vcf("large.vcf", chunk_size=10_000):
    process(chunk)  # each chunk is a Polars DataFrame
```

### Pandas output

```python
from vcfv import read_vcf_pandas

df = read_vcf_pandas("variants.vcf")  # returns a Pandas DataFrame
```

### Incomplete INFO/FORMAT headers

Some VCF files have INFO or FORMAT fields in the data that are not declared in the header. By default vcfv reads keys only from the header (`infer_info_keys_from="header"`) which is fastest. If you suspect your file has undeclared fields you can scan a sample of rows or the entire file:

```python
# Scan first 50,000 rows to detect undeclared INFO keys
# Emits a UserWarning if any undeclared keys are found
df = read_vcf("variants.vcf", infer_info_keys_from=50_000)

# Scan the entire file — safe but slower (streams in chunks, no full RAM load)
df = read_vcf("variants.vcf", infer_info_keys_from="all")

# Same options available for FORMAT keys
df = read_vcf("variants.vcf", infer_format_keys_from="all")
```

## API reference

### `read_vcf`

```python
read_vcf(
    path: str | Path,
    *,
    lazy: bool = False,
    parse_info: False | "wide" | "struct" | "auto" = "auto",
    infer_info_keys_from: int | "header" | "all" = "header",
    parse_format: False | "wide" | "struct" | "auto" = "auto",
    infer_format_keys_from: int | "header" | "all" = "header",
    min_qual: float | None = None,
    region: str | None = None,
    fields: list[str] | None = None,
) -> pl.DataFrame | pl.LazyFrame
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | `str \| Path` | — | Path to `.vcf` or `.vcf.gz` file |
| `lazy` | `bool` | `False` | Return a `LazyFrame` instead of `DataFrame` |
| `parse_info` | see below | `"auto"` | How to handle the INFO column |
| `infer_info_keys_from` | `int \| "header" \| "all"` | `"header"` | Where to discover INFO field keys |
| `parse_format` | see below | `"auto"` | How to handle FORMAT and sample columns |
| `infer_format_keys_from` | `int \| "header" \| "all"` | `"header"` | Where to discover FORMAT field keys |
| `min_qual` | `float \| None` | `None` | Keep only rows where `QUAL >= min_qual`. Rows with `QUAL=.` are excluded |
| `region` | `str \| None` | `None` | Genomic region filter in format `"chr1:1000000-2000000"` |
| `fields` | `list[str] \| None` | `None` | Select specific output columns by name |

### `parse_info` and `parse_format` options

| Value | Behaviour |
|-------|-----------|
| `"auto"` | Picks the best strategy automatically (see below) |
| `"wide"` | Each field becomes a separate typed column (`INFO_AF`, `Sample1_GT`, ...) |
| `"struct"` | Fields stored as a list of strings per row — memory efficient for many samples |
| `False` | No parsing — raw strings kept as-is |

`parse_format="auto"` selects:
- `"wide"` for ≤ 20 samples
- `"struct"` for ≤ 200 samples
- `False` for > 200 samples

`parse_info="auto"` always selects `"wide"`.

### `infer_info_keys_from` and `infer_format_keys_from` options

| Value | Behaviour |
|-------|-----------|
| `"header"` | Read keys from `##INFO`/`##FORMAT` header lines — fastest, default |
| `int` (e.g. `10_000`) | Scan first N rows and merge with header keys — emits `UserWarning` for undeclared keys |
| `"all"` | Stream entire file in chunks to find all keys — safe for incomplete headers, slowest |

### `iter_vcf`

```python
iter_vcf(
    path: str | Path,
    chunk_size: int = 10_000,
    *,
    parse_info: False | "wide" | "struct" | "auto" = "auto",
    infer_info_keys_from: int | "header" | "all" = "header",
    parse_format: False | "wide" | "struct" | "auto" = "auto",
    infer_format_keys_from: int | "header" | "all" = "header",
    min_qual: float | None = None,
    region: str | None = None,
    fields: list[str] | None = None,
) -> Iterator[pl.DataFrame]
```

Yields `chunk_size` rows at a time as Polars DataFrames. Accepts all the same parameters as `read_vcf`.

## Benchmarks

Tested on 500,000 variants, 10 runs, trimmed mean (top/bottom 10% dropped).
RAM measured via `psutil` RSS delta per subprocess (includes Rust/C heap).
Tested on: Windows 11, AMD Ryzen 7 7730U, 16 GB RAM.

### vcfv

| Mode | Mean | Median | Stdev | RAM |
|------|------|--------|-------|-----|
| eager (INFO+FORMAT expanded, header) | 3.39s | 3.38s | ±0.31s | 570 MB |
| lazy (INFO+FORMAT expanded, header) | 3.55s | 3.57s | ±0.11s | 571 MB |
| eager (INFO+FORMAT expanded, all) | 9.71s | 9.70s | ±0.32s | 646 MB |
| eager (no expansion) | 0.15s | 0.14s | ±0.01s | 273 MB |
| lazy (no expansion) | 0.15s | 0.15s | ±0.01s | 277 MB |

### Baselines (no INFO/FORMAT expansion — apples-to-apples)

| Tool | Mean | Median | Stdev | RAM |
|------|------|--------|-------|-----|
| scikit-allel | 2.10s | 2.10s | ±0.05s | 115 MB |
| pandas raw TSV | 3.23s | 3.21s | ±0.08s | 358 MB |

**vcfv with no expansion is ~14x faster than scikit-allel** (0.15s vs 2.10s).

Neither scikit-allel nor pandas natively expand INFO or FORMAT fields —
vcfv is the only tool in this comparison that does so in a single call.

> To reproduce: `python benchmarks/benchmark.py your_file.vcf --runs 10`

## Supported formats

| Format | Support |
|--------|---------|
| `.vcf` | ✅ Full lazy streaming |
| `.vcf.gz` | ✅ Lazy streaming (from v0.3.0) |
| `.bcf` | ❌ Not supported yet |

## Requirements

- Python ≥ 3.11
- Polars ≥ 1.0
- PyArrow ≥ 14.0

## Contributing

Issues and pull requests are welcome.
Please open an issue before submitting a PR for larger changes.

## License

MIT