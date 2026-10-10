import time
import polars as pl
from vcfv import read_vcf

start = time.perf_counter()

df = read_vcf("fixtures/samples_bcf.bcf", lazy=True)

