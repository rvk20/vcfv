import re
import gzip
from pathlib import Path


def _open(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


def parse_headers(path: Path) -> tuple[int, dict, list[str]]:
    meta = {"INFO": {}, "FORMAT": {}}
    skip = 0
    header_cols = None

    with _open(path) as f:
        for line in f:
            if line.startswith("##"):
                skip += 1
                _parse_meta_line(line, meta)
            else:
                header_cols = line.strip().split("\t")
                break

    return skip, meta, header_cols


def _parse_meta_line(line: str, meta: dict) -> None:
    # ##INFO=<ID=AF,Number=A,Type=Float,Description="Allele freq">
    m = re.match(r'##(INFO|FORMAT)=<ID=(\w+),.*?Type=(\w+)', line)
    if m:
        kind, field_id, field_type = m.groups()
        meta[kind][field_id] = field_type