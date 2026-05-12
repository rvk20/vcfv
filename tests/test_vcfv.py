"""
Tests for the vcfv library.

Run with: pytest -v
"""
import warnings
import pytest
import polars as pl
from pathlib import Path

FIXTURES        = Path(__file__).parent / "fixtures"
MULTI_SAMPLE    = FIXTURES / "multi_sample.vcf"
MULTI_SAMPLE_GZ = FIXTURES / "multi_sample.vcf.gz"
NO_SAMPLES      = FIXTURES / "no_samples.vcf"
MISSING_VALUES  = FIXTURES / "missing_values.vcf"
MULTIALLELIC    = FIXTURES / "multiallelic.vcf"
VARYING_FORMAT  = FIXTURES / "varying_format.vcf"
MANY_SAMPLES    = FIXTURES / "many_samples.vcf"
FLAGS_ONLY      = FIXTURES / "flags_only.vcf"
NO_INFO_HEADERS = FIXTURES / "no_info_headers.vcf"


# ---------------------------------------------------------------------------
# read_vcf — basic behaviour
# ---------------------------------------------------------------------------

class TestReadVcfBasic:

    def test_returns_dataframe(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE)
        assert isinstance(df, pl.DataFrame)

    def test_returns_lazyframe_when_lazy_true(self):
        from vcfv import read_vcf
        lf = read_vcf(MULTI_SAMPLE, lazy=True)
        assert isinstance(lf, pl.LazyFrame)

    def test_chrom_column_renamed(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE)
        assert "CHROM" in df.columns
        assert "#CHROM" not in df.columns

    def test_row_count(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE)
        assert len(df) == 4

    def test_file_without_samples(self):
        from vcfv import read_vcf
        df = read_vcf(NO_SAMPLES)
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 3


# ---------------------------------------------------------------------------
# read_vcf — gzip support
# ---------------------------------------------------------------------------

class TestReadVcfGzip:

    def test_reads_vcf_gz(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE_GZ)
        assert isinstance(df, pl.DataFrame)

    def test_gz_and_plain_produce_same_data(self):
        from vcfv import read_vcf
        df_plain = read_vcf(MULTI_SAMPLE, parse_info=False, parse_format=False)
        df_gz    = read_vcf(MULTI_SAMPLE_GZ, parse_info=False, parse_format=False)
        assert df_plain.shape == df_gz.shape
        assert df_plain["POS"].to_list() == df_gz["POS"].to_list()


# ---------------------------------------------------------------------------
# parse_info — INFO column
# ---------------------------------------------------------------------------

class TestParseInfo:

    def test_wide_creates_info_columns(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info="wide", parse_format=False)
        assert "INFO_AC" in df.columns
        assert "INFO_AF" in df.columns
        assert "INFO_DP" in df.columns

    def test_wide_flag_db_present(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info="wide", parse_format=False)
        assert "INFO_DB" in df.columns
        db_values = df["INFO_DB"].to_list()
        assert db_values[0] is not None
        assert db_values[3] is None

    def test_wide_flag_somatic_present(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info="wide", parse_format=False)
        assert "INFO_SOMATIC" in df.columns
        somatic_values = df["INFO_SOMATIC"].to_list()
        assert somatic_values[2] is not None
        assert somatic_values[0] is None

    def test_false_does_not_add_info_columns(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info=False, parse_format=False)
        info_cols = [c for c in df.columns if c.startswith("INFO_")]
        assert info_cols == []

    def test_struct_converts_info_to_list(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info="struct", parse_format=False)
        assert df["INFO"].dtype == pl.List(pl.String)

    def test_missing_qual_is_null(self):
        from vcfv import read_vcf
        df = read_vcf(MISSING_VALUES, parse_info=False, parse_format=False)
        qual_values = df["QUAL"].to_list()
        assert qual_values[1] is None
        assert qual_values[3] is None

    def test_missing_info_dot_does_not_crash(self):
        from vcfv import read_vcf
        df = read_vcf(MISSING_VALUES, parse_info="wide", parse_format=False)
        assert isinstance(df, pl.DataFrame)

    def test_flags_only_info(self):
        from vcfv import read_vcf
        df = read_vcf(FLAGS_ONLY, parse_info="wide", parse_format=False)
        assert "INFO_DB" in df.columns
        assert "INFO_SOMATIC" in df.columns

    def test_flags_only_values(self):
        from vcfv import read_vcf
        df = read_vcf(FLAGS_ONLY, parse_info="wide", parse_format=False)
        db      = df["INFO_DB"].to_list()
        somatic = df["INFO_SOMATIC"].to_list()
        assert db[0] is not None
        assert somatic[0] is not None
        assert db[1] is not None
        assert somatic[1] is None
        assert db[2] is None
        assert somatic[2] is not None

    def test_multiallelic_af_field(self):
        from vcfv import read_vcf
        df = read_vcf(MULTIALLELIC, parse_info="wide", parse_format=False)
        assert "INFO_AF" in df.columns
        assert isinstance(df, pl.DataFrame)


# ---------------------------------------------------------------------------
# infer_info_keys_from
# ---------------------------------------------------------------------------

class TestInferInfoKeysFrom:

    def test_header_uses_declared_keys(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info="wide", parse_format=False, infer_info_keys_from="header")
        assert "INFO_AC" in df.columns
        assert "INFO_AF" in df.columns

    def test_all_streaming_finds_same_keys(self):
        from vcfv import read_vcf
        df_header = read_vcf(MULTI_SAMPLE, parse_info="wide", parse_format=False, infer_info_keys_from="header")
        df_all    = read_vcf(MULTI_SAMPLE, parse_info="wide", parse_format=False, infer_info_keys_from="all")
        info_cols_header = sorted(c for c in df_header.columns if c.startswith("INFO_"))
        info_cols_all    = sorted(c for c in df_all.columns if c.startswith("INFO_"))
        assert info_cols_header == info_cols_all

    def test_sample_rows_finds_keys(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info="wide", parse_format=False, infer_info_keys_from=100)
        assert "INFO_AC" in df.columns

    def test_sample_rows_warns_on_undeclared_keys(self):
        from vcfv import read_vcf
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            read_vcf(NO_INFO_HEADERS, parse_info="wide", parse_format=False, infer_info_keys_from=10)
        user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warnings) > 0
        assert "not declared in header" in str(user_warnings[0].message)


# ---------------------------------------------------------------------------
# parse_format — sample columns
# ---------------------------------------------------------------------------

class TestParseFormat:

    def test_wide_creates_sample_columns(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info=False, parse_format="wide")
        assert "Sample1_GT" in df.columns
        assert "Sample1_DP" in df.columns
        assert "Sample2_GT" in df.columns

    def test_wide_gt_values(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info=False, parse_format="wide")
        assert df["Sample1_GT"][0] == "1/1"

    def test_false_does_not_parse_format(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info=False, parse_format=False)
        sample_gt_cols = [c for c in df.columns if c.endswith("_GT")]
        assert sample_gt_cols == []

    def test_auto_selects_wide_for_few_samples(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info=False, parse_format="auto")
        assert "Sample1_GT" in df.columns

    def test_no_samples_does_not_raise(self):
        from vcfv import read_vcf
        df = read_vcf(NO_SAMPLES, parse_format="auto")
        assert isinstance(df, pl.DataFrame)

    def test_auto_selects_struct_for_many_samples(self):
        from vcfv import read_vcf
        df = read_vcf(MANY_SAMPLES, parse_info=False, parse_format="auto")
        assert "S1_GT" not in df.columns
        assert "S1" in df.columns

    def test_varying_format_per_row_does_not_crash(self):
        from vcfv import read_vcf
        df = read_vcf(VARYING_FORMAT, parse_info=False, parse_format="wide")
        assert isinstance(df, pl.DataFrame)
        assert "Sample1_GT" in df.columns

    def test_varying_format_missing_field_is_null(self):
        from vcfv import read_vcf
        df = read_vcf(VARYING_FORMAT, parse_info=False, parse_format="wide")
        ad_values = df["Sample1_AD"].to_list()
        assert ad_values[0] is not None
        assert ad_values[1] is None
        assert ad_values[2] is not None


# ---------------------------------------------------------------------------
# infer_format_keys_from
# ---------------------------------------------------------------------------

class TestInferFormatKeysFrom:

    def test_header_uses_declared_keys(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info=False, parse_format="wide", infer_format_keys_from="header")
        assert "Sample1_GT" in df.columns
        assert "Sample1_DP" in df.columns

    def test_all_streaming_finds_same_keys(self):
        from vcfv import read_vcf
        df_header = read_vcf(MULTI_SAMPLE, parse_info=False, parse_format="wide", infer_format_keys_from="header")
        df_all    = read_vcf(MULTI_SAMPLE, parse_info=False, parse_format="wide", infer_format_keys_from="all")
        fmt_cols_header = sorted(c for c in df_header.columns if c.startswith("Sample1_"))
        fmt_cols_all    = sorted(c for c in df_all.columns if c.startswith("Sample1_"))
        assert fmt_cols_header == fmt_cols_all

    def test_sample_rows_finds_keys(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info=False, parse_format="wide", infer_format_keys_from=100)
        assert "Sample1_GT" in df.columns


# ---------------------------------------------------------------------------
# filtering
# ---------------------------------------------------------------------------

class TestFiltering:

    def test_min_qual(self):
        from vcfv import read_vcf
        df = read_vcf(MULTI_SAMPLE, parse_info=False, parse_format=False, min_qual=300.0)
        assert all(q >= 300.0 for q in df["QUAL"].to_list())

    def test_min_qual_excludes_null_qual(self):
        from vcfv import read_vcf
        df = read_vcf(MISSING_VALUES, parse_info=False, parse_format=False, min_qual=1.0)
        assert all(q is not None for q in df["QUAL"].to_list())

    def test_region(self):
        from vcfv import read_vcf
        df = read_vcf(
            MULTI_SAMPLE,
            parse_info=False,
            parse_format=False,
            region="chr5:100000000-200000000",
        )
        assert len(df) == 1
        assert df["CHROM"][0] == "chr5"

    def test_region_no_match_returns_empty(self):
        from vcfv import read_vcf
        df = read_vcf(
            MULTI_SAMPLE,
            parse_info=False,
            parse_format=False,
            region="chr99:1-1000",
        )
        assert len(df) == 0

    def test_invalid_region_format_raises(self):
        from vcfv import read_vcf
        with pytest.raises(ValueError, match="Invalid region format"):
            read_vcf(MULTI_SAMPLE, region="chr1")


# ---------------------------------------------------------------------------
# validation and errors
# ---------------------------------------------------------------------------

class TestValidation:

    def test_missing_file_raises(self):
        from vcfv import read_vcf
        with pytest.raises(FileNotFoundError):
            read_vcf("does_not_exist.vcf")

    def test_unsupported_extension_raises(self, tmp_path):
        from vcfv import read_vcf
        bad_file = tmp_path / "file.txt"
        bad_file.write_text("dummy")
        with pytest.raises(ValueError, match="Unsupported file format"):
            read_vcf(bad_file)


# ---------------------------------------------------------------------------
# iter_vcf
# ---------------------------------------------------------------------------

class TestIterVcf:

    def test_returns_chunks(self):
        from vcfv import iter_vcf
        chunks = list(iter_vcf(MULTI_SAMPLE, chunk_size=2, parse_info=False, parse_format=False))
        assert len(chunks) == 2

    def test_all_rows_across_chunks(self):
        from vcfv import iter_vcf
        chunks = list(iter_vcf(MULTI_SAMPLE, chunk_size=2, parse_info=False, parse_format=False))
        total = sum(len(c) for c in chunks)
        assert total == 4

    def test_each_chunk_is_dataframe(self):
        from vcfv import iter_vcf
        for chunk in iter_vcf(MULTI_SAMPLE, chunk_size=2, parse_info=False, parse_format=False):
            assert isinstance(chunk, pl.DataFrame)

    def test_chunk_size_larger_than_file(self):
        from vcfv import iter_vcf
        chunks = list(iter_vcf(MULTI_SAMPLE, chunk_size=1000, parse_info=False, parse_format=False))
        assert len(chunks) == 1
        assert len(chunks[0]) == 4

    def test_iter_vcf_with_parse_info(self):
        from vcfv import iter_vcf
        chunks = list(iter_vcf(MULTI_SAMPLE, chunk_size=2, parse_info="wide", parse_format=False))
        assert all("INFO_AC" in c.columns for c in chunks)

    def test_iter_vcf_with_min_qual(self):
        from vcfv import iter_vcf
        chunks = list(iter_vcf(MULTI_SAMPLE, chunk_size=2, parse_info=False, parse_format=False, min_qual=300.0))
        total = sum(len(c) for c in chunks)
        assert total < 4