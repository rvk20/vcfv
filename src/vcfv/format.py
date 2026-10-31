from __future__ import annotations

import polars as pl


def resolve_parse_format(parse_format, sample_count):
    if parse_format != "auto":
        return parse_format

    if sample_count == 0:
        return False

    if sample_count <= 20:
        return "wide"
    elif sample_count <= 200:
        return "struct"
    else:
        return False


def apply_format_strategy(
    lf: pl.LazyFrame,
    parse_format,
    header_cols: list[str],
    format_meta: dict,
    infer_format_keys_from: int | str = "header",
) -> pl.LazyFrame:
    if parse_format is False:
        return lf

    sample_cols = header_cols[9:]

    if parse_format == "wide":
        return _apply_format_wide(lf, sample_cols, format_meta, infer_format_keys_from)

    if parse_format == "struct":
        return _apply_format_struct(lf, sample_cols)

    return lf


def _apply_format_struct(
    lf: pl.LazyFrame,
    sample_cols: list[str],
) -> pl.LazyFrame:
    format_keys = pl.col("FORMAT").str.split(":")

    exprs = []
    for col in sample_cols:
        exprs.append(
            pl.struct(
                [
                    format_keys.alias("keys"),
                    pl.col(col).str.split(":").alias("values"),
                ]
            ).alias(col)
        )

    return lf.with_columns(exprs)


def _collect_format_keys(
    lf: pl.LazyFrame,
    format_meta: dict,
    infer_from: int | str = "header",
) -> list[str]:
    if infer_from == "header":
        if format_meta:
            return list(format_meta.keys())
        return _collect_format_keys_from_first_row(lf)

    if infer_from == "all":
        return _collect_format_keys_streaming(lf)

    if format_meta:
        header_keys = set(format_meta.keys())
    else:
        header_keys = set(_collect_format_keys_from_first_row(lf))

    sample_keys = set(
        lf.head(infer_from)
        .select(pl.col("FORMAT").str.split(":").explode().unique())
        .collect()
        .to_series()
        .to_list()
    )

    undeclared = sample_keys - header_keys
    if undeclared:
        import warnings
        warnings.warn(
            f"Found FORMAT keys not declared in header: {sorted(undeclared)}. "
            f"Detected from first {infer_from} rows only — "
            "further undeclared keys may exist.",
            UserWarning,
            stacklevel=3,
        )

    return list(header_keys | sample_keys)


def _collect_format_keys_from_first_row(lf: pl.LazyFrame) -> list[str]:
    first_format = (
        lf.select(pl.col("FORMAT").first())
        .collect()
        .item()
    )
    return first_format.split(":")


def _collect_format_keys_streaming(lf: pl.LazyFrame) -> list[str]:
    all_keys: set[str] = set()
    offset = 0
    chunk_size = 10_000

    while True:
        chunk_keys = (
            lf.slice(offset, chunk_size)
            .select(pl.col("FORMAT").str.split(":").explode().unique())
            .collect()
            .to_series()
            .to_list()
        )

        if not chunk_keys:
            break

        all_keys.update(chunk_keys)
        offset += chunk_size

    return list(all_keys)


def _apply_format_wide(
    lf: pl.LazyFrame,
    sample_cols: list[str],
    format_meta: dict,
    infer_from: int | str = "header",
) -> pl.LazyFrame:
    format_keys = _collect_format_keys(lf, format_meta, infer_from)
    format_parts = pl.col("FORMAT").str.split(":")
    exprs = []

    for sample in sample_cols:
        values = pl.col(sample).str.split(":")

        for key in format_keys:
            key_position = (
                pl.when(format_parts.list.contains(key))
                .then(
                    format_parts
                    .list.eval(pl.element() == pl.lit(key))
                    .list.arg_max()
                )
                .otherwise(None)
            )

            exprs.append(
                values.list.get(
                    key_position,
                    null_on_oob=True,
                ).alias(f"{sample}_{key}")
            )

    return lf.with_columns(exprs)