from .reader import read_vcf, iter_vcf

__version__ = "0.2.0"

def read_vcf_pandas(path, **kwargs):
    try:
        import pandas
    except ImportError:
        raise ImportError(
            "Pandas is not installed."
            "Install it via: pip install vcfv[pandas]"
        )
    return read_vcf(path, **kwargs).to_pandas()

__all__ = ["read_vcf", "iter_vcf", "read_vcf_pandas"]