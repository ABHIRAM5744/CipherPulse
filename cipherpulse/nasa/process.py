"""Inspect and clean downloaded NASA files. Keeps the original, writes a processed CSV and a provenance sidecar.
Never treats specialized scientific formats as CSV."""
import csv
import io
import json
import re
import zipfile
from pathlib import Path

import pandas as pd

from . import labels
from .http import iso_now
from .osdr import classify_file

UNIT_RE = re.compile(r"[\(\[]\s*([A-Za-zµμ%/°][^\)\]]{0,18})\s*[\)\]]\s*$")
MAX_INSPECT_ROWS = 200_000
MAX_ZIP_TOTAL = 100 * 1024 * 1024


def _sniff(sample: str) -> str:
    counts = {"\t": sample.count("\t"), ",": sample.count(","), ";": sample.count(";")}
    d = max(counts, key=counts.get)
    return d if counts[d] else "\t"


def _units(columns):
    out = {}
    for c in columns:
        m = UNIT_RE.search(str(c))
        if m:
            out[str(c)] = m.group(1).strip()
    return out  # only units stated in the file's own headers; nothing is assumed


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all").dropna(axis=1, how="all")
    for c in df.columns:
        if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c]):
            txt = df[c].astype("string").str.strip()
            txt = txt.mask(txt.isin(["", "NA", "NaN", "nan", "NULL", "null"]))
            num = pd.to_numeric(txt, errors="coerce")
            if txt.notna().sum() and num.notna().sum() / txt.notna().sum() >= 0.9:
                df[c] = num.astype("float64")
    return df


def describe_table(name, df, raw_columns=None):
    num = df.select_dtypes("number")
    stats = {c: {"min": float(num[c].min()), "max": float(num[c].max()), "mean": float(num[c].mean()), "n": int(num[c].notna().sum())} for c in num.columns[:60]}
    return {"name": name, "rows": int(len(df)), "columns": list(map(str, df.columns))[:200], "n_columns": int(df.shape[1]),
            "missing": {str(c): int(v) for c, v in df.isna().sum().items() if v}, "numeric_columns": list(map(str, num.columns))[:200],
            "numeric_summary": stats, "units": _units(raw_columns if raw_columns is not None else df.columns),
            "usable_records": int(num.notna().any(axis=1).sum()) if len(num.columns) else 0}


def _read_text_table(data: bytes):
    text = data.decode("utf-8", errors="replace")
    d = _sniff(text[:8192])
    df = pd.read_csv(io.StringIO(text), sep=d, engine="python" if d == ";" else "c", on_bad_lines="skip", nrows=MAX_INSPECT_ROWS, dtype=str) if "\n" in text else pd.DataFrame()
    return df, d


def _isa_investigation(data: bytes):
    rows = list(csv.reader(io.StringIO(data.decode("utf-8", errors="replace")), delimiter="\t"))
    return {r[0]: [x for x in r[1:] if x] for r in rows if r and r[0] and not r[0].startswith("#")}


def process_file(path: Path, acc: str, title=None, source_url="", download=None, organism=None) -> dict:
    path = Path(path)
    info = classify_file(path.name)
    rep = {"accession": acc, "dataset_title": title, "organism": organism, "file": path.name, "format": info["format"], "label": "NASA_RESEARCH",
           "source_url": source_url, "retrieved_at": iso_now(), "download": download, "tables": [], "units": {}, "usable_records": 0,
           "processing_method": "cipherpulse.nasa.process (pandas)", "status": "processed"}
    outdir = labels.NASA_DIR / "processed" / acc
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        if not info["processable"]:
            rep.update(status="unsupported_format", suggested_parser=info["parser"], note="Specialized format; not parsed as CSV.")
        elif path.suffix.lower() == ".zip":
            _zip(path, rep, outdir)
        elif path.suffix.lower() in (".xlsx", ".xls"):
            for sheet, df in pd.read_excel(path, sheet_name=None, dtype=str).items():
                _add_table(rep, outdir, f"{path.stem}__{sheet}", df)
        elif path.suffix.lower() == ".json":
            obj = json.loads(path.read_text(errors="replace"))
            df = pd.json_normalize(obj if isinstance(obj, list) else [obj]) if not isinstance(obj, dict) or not all(isinstance(v, dict) for v in obj.values()) else pd.json_normalize(list(obj.values()))
            _add_table(rep, outdir, path.stem, df.astype(object))
        else:
            df, d = _read_text_table(path.read_bytes())
            rep["delimiter"] = repr(d)
            _add_table(rep, outdir, path.stem, df)
    except Exception as e:  # report, never crash the pipeline
        rep.update(status="failed", error=f"{type(e).__name__}: {e}")
    for t in rep["tables"]:
        rep["units"].update(t["units"])
        rep["usable_records"] += t["usable_records"]
    if rep["status"] == "processed" and not rep["tables"]:
        rep["status"] = "no_tables_found"
    rep["sidecar"] = labels.write_sidecar(f"{acc}__{path.name}", rep)
    return rep


def _add_table(rep, outdir: Path, name, df):
    raw_cols = list(df.columns)
    clean = _clean(df)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    out = outdir / f"{safe}.csv"
    clean.to_csv(out, index=False)
    t = describe_table(name, clean, raw_cols)
    t["processed_csv"] = str(out)
    rep["tables"].append(t)


def _zip(path, rep, outdir):
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        total = sum(i.file_size for i in infos)
        rep["archive_members"] = [{"name": i.filename, "size": i.file_size} for i in infos][:200]
        if total > MAX_ZIP_TOTAL:
            raise ValueError(f"archive expands to {total/1e6:.0f} MB, over the safety limit")
        for i in infos:
            n = i.filename
            base = Path(n).name
            if i.is_dir() or ".." in n or n.startswith("/"):
                continue
            low = base.lower()
            data = None
            if re.match(r"^i_.*\.txt$", low):  # ISA-Tab investigation: key / values layout
                rep.setdefault("isa_investigation", _isa_investigation(z.read(n)))
            elif low.endswith((".txt", ".tsv", ".csv")):
                data = z.read(n)
            if data:
                df, _ = _read_text_table(data)
                if df.shape[1] >= 2:
                    _add_table(rep, outdir, Path(base).stem, df)
