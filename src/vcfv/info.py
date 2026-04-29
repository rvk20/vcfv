import polars as pl


def resolve_parse_info(parse_info):
    if parse_info != "auto":
        return parse_info

    return "wide"


def apply_info_strategy(lf: pl.LazyFrame, parse_info):
    if parse_info is False:
        return lf

    if parse_info == "wide":
        return _apply_info_wide(lf)

    if parse_info == "struct":
        return _apply_info_struct(lf)

    return lf


def _apply_info_struct(lf: pl.LazyFrame) -> pl.LazyFrame:
    return lf.with_columns(
        pl.col("INFO")
        .str.split(";")
        .alias("INFO")
    )


def _collect_info_keys(
    lf: pl.LazyFrame,
    sample_rows: int = 1000,
) -> list[str]:

    return (
        lf.head(sample_rows)
        .select(
            pl.col("INFO")
            .str.split(";")
            .explode()
            .alias("pair")
        )
        .filter(pl.col("pair") != ".")
        .select(
            pl.col("pair")
            .str.split("=")
            .list.first()
            .unique()
            .sort()
        )
        .collect()
        .to_series()
        .to_list()
    )


def _maybe_cast(expr: pl.Expr) -> pl.Expr:

    return pl.coalesce(
        expr.cast(pl.Int64, strict=False),
        expr.cast(pl.Float64, strict=False),
        expr
    )


def _apply_info_wide(lf: pl.LazyFrame) -> pl.LazyFrame:

    info_keys = _collect_info_keys(lf)

    if not info_keys:
        return lf

    info_pairs = pl.col("INFO").str.split(";")

    exprs = []

    for key in info_keys:

        value_expr = (
            info_pairs
            .list.eval(
                pl.when(
                    pl.element().str.starts_with(f"{key}=")
                )
                .then(
                    pl.element()
                    .str.split("=")
                    .list.get(1, null_on_oob=True)
                )
                .when(
                    pl.element() == key
                )
                .then(pl.lit(True))
                .otherwise(None)
            )
            .list.drop_nulls()
            .list.get(0, null_on_oob=True)
        )

        exprs.append(
            _maybe_cast(value_expr).alias(f"INFO_{key}")
        )

    return lf.with_columns(exprs)