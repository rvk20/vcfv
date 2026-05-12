from __future__ import annotations

import polars as pl
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal


def resolve_parse_info(parse_info):
    if parse_info != "auto":
        return parse_info
    return "wide"


def apply_info_strategy(
    lf: pl.LazyFrame,
    parse_info,
    meta_info: dict,
    infer_info_keys_from: int | str = "header",
) -> pl.LazyFrame:
    if parse_info is False:
        return lf

    if parse_info == "wide":
        return _apply_info_wide(lf, meta_info, infer_info_keys_from)

    if parse_info == "struct":
        return _apply_info_struct(lf)

    return lf


def _apply_info_struct(lf: pl.LazyFrame) -> pl.LazyFrame:
    return lf.with_columns(
        pl.col("INFO").str.split(";").alias("INFO")
    )


def _collect_info_keys(
    lf: pl.LazyFrame,
    meta_info: dict,
    infer_from: int | str = "header",
) -> list[str]:
    if infer_from == "header":
        return list(meta_info.keys())

    if infer_from == "all":
        return _collect_info_keys_streaming(lf)

    header_keys = set(meta_info.keys())
    sample_keys = set(
        lf.head(infer_from)
        .select(pl.col("INFO").str.split(";").explode().alias("pair"))
        .filter(pl.col("pair") != ".")
        .select(pl.col("pair").str.split("=").list.first().unique())
        .collect()
        .to_series()
        .to_list()
    )

    undeclared = sample_keys - header_keys
    if undeclared:
        import warnings
        warnings.warn(
            f"Found INFO keys not declared in header: {sorted(undeclared)}. "
            f"Detected from first {infer_from} rows only — "
            "further undeclared keys may exist.",
            UserWarning,
            stacklevel=3,
        )

    return sorted(header_keys | sample_keys)


def _collect_info_keys_streaming(lf: pl.LazyFrame) -> list[str]:
    all_keys: set[str] = set()
    offset = 0
    chunk_size = 10_000

    while True:
        chunk_keys = (
            lf.slice(offset, chunk_size)
            .select(pl.col("INFO").str.split(";").explode().alias("pair"))
            .filter(pl.col("pair") != ".")
            .select(pl.col("pair").str.split("=").list.first().unique())
            .collect()
            .to_series()
            .to_list()
        )

        if not chunk_keys:
            break

        all_keys.update(chunk_keys)
        offset += chunk_size

    return sorted(all_keys)


def _maybe_cast(expr: pl.Expr) -> pl.Expr:
    return pl.coalesce(
        expr.cast(pl.Int64, strict=False),
        expr.cast(pl.Float64, strict=False),
        expr,
    )


def _apply_info_wide(
    lf: pl.LazyFrame,
    meta_info: dict,
    infer_from: int | str = "header",
) -> pl.LazyFrame:
    info_keys = _collect_info_keys(lf, meta_info, infer_from)

    if not info_keys:
        return lf

    info_pairs = pl.col("INFO").str.split(";")
    exprs = []

    for key in info_keys:
        value_expr = (
            info_pairs
            .list.eval(
                pl.when(pl.element().str.starts_with(f"{key}="))
                .then(
                    pl.element()
                    .str.split("=")
                    .list.get(1, null_on_oob=True)
                )
                .when(pl.element() == key)
                .then(pl.lit(True))
                .otherwise(None)
            )
            .list.drop_nulls()
            .list.get(0, null_on_oob=True)
        )
        exprs.append(_maybe_cast(value_expr).alias(f"INFO_{key}"))

    return lf.with_columns(exprs)