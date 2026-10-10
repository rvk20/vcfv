import gzip
import io
import polars as pl
from pathlib import Path
from typing import Iterator, Literal
from .schema import parse_headers
from .format import apply_format_strategy, resolve_parse_format
from .info import apply_info_strategy, resolve_parse_info


def _scan_vcf(path: Path, skip_rows: int) -> pl.LazyFrame:
    return pl.scan_csv(
                path,
                separator="\t",
                skip_rows=skip_rows,
                has_header=True,
                comment_prefix=None,
                infer_schema_length=1000,
            )


def read_vcf(
    path: str | Path,
    *,
    lazy: bool = False,
    parse_info: Literal[False, "wide", "struct", "auto"] = "auto",
    infer_info_keys_from: int | Literal["header", "all"] = "header",
    parse_format: Literal[False, "wide", "struct", "auto"] = "auto",
    infer_format_keys_from: int | Literal["header", "all"] = "header",
    min_qual: float | None = None,
    region: str | None = None,
    fields: list[str] | None = None,
) -> pl.DataFrame | pl.LazyFrame:

    path = Path(path)
    _validate_path(path)

    skip_rows, meta, header_cols = parse_headers(path)
    sample_count = max(0, len(header_cols) - 9)

    parse_info = resolve_parse_info(parse_info)
    parse_format = resolve_parse_format(parse_format, sample_count)
    _validate_format_request(parse_format, header_cols)

    lf = _scan_vcf(path, skip_rows).rename({"#CHROM": "CHROM"})

    lf = lf.with_columns(
        pl.col("QUAL").cast(pl.Float64, strict=False)
    )

    lf = apply_info_strategy(lf, parse_info, meta["INFO"], infer_info_keys_from)
    lf = apply_format_strategy(lf, parse_format, header_cols, meta["FORMAT"], infer_format_keys_from)

    if min_qual is not None:
        lf = lf.filter(pl.col("QUAL") >= min_qual)

    if region is not None:
        chrom, pos = _parse_region(region)
        lf = lf.filter(
            (pl.col("CHROM") == chrom) &
            (pl.col("POS") >= pos[0]) &
            (pl.col("POS") <= pos[1])
        )

    if fields is not None:
        lf = lf.select(fields)

    return lf if lazy else lf.collect()


def iter_vcf(
    path: str | Path,
    chunk_size: int = 10_000,
    **kwargs,
) -> Iterator[pl.DataFrame]:
    lf = read_vcf(path, lazy=True, **kwargs)
    offset = 0

    while True:
        chunk = lf.slice(offset, chunk_size).collect()
        if chunk.is_empty():
            break
        yield chunk
        offset += chunk_size


def _validate_path(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"The file does not exist: {path}")
    allowed = {".vcf", ".gz"}
    if path.suffix not in allowed:
        raise ValueError(
            f"Unsupported file format: {path.suffix!r}. "
            "Supported formats: .vcf, .vcf.gz"
        )


def _parse_region(region: str) -> tuple[str, tuple[int, int]]:
    try:
        chrom, coords = region.split(":")
        start, end = coords.split("-")
        return chrom, (int(start), int(end))
    except ValueError:
        raise ValueError(
            f"Invalid region format: {region!r}. "
            "Expected format: 'chr1:1000000-2000000'"
        )


def _validate_format_request(parse_format, header_cols):
    has_format = len(header_cols) >= 9
    sample_count = max(0, len(header_cols) - 9)

    if parse_format in ("wide", "struct"):
        if not has_format:
            raise ValueError(
                "FORMAT parsing requested but FORMAT column missing"
            )
        if sample_count == 0:
            raise ValueError(
                "FORMAT parsing requested but no sample columns present"
            )