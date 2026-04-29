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


def apply_format_strategy(lf, parse_format, header_cols, format_meta):
    if parse_format is False:
        return lf

    sample_cols = header_cols[9:]

    if parse_format == "wide":
        return _apply_format_wide(lf, sample_cols, format_meta)

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


def _apply_format_wide(
    lf: pl.LazyFrame,
    sample_cols: list[str],
    format_meta: dict,
) -> pl.LazyFrame:
    format_keys = _collect_format_keys_fallback(lf)

    exprs = []

    for sample in sample_cols:
        values = pl.col(sample).str.split(":")

        for i, key in enumerate(format_keys):
            exprs.append(
                values.list.get(i, null_on_oob=True).alias(f"{sample}_{key}")
            )

    return lf.with_columns(exprs)


def _collect_format_keys_fallback(lf: pl.LazyFrame) -> list[str]:
    first_format = (
        lf.select(pl.col("FORMAT").first())
        .collect()
        .item()
    )
    return first_format.split(":")