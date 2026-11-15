"""NASA Open Science Data Repository: discovery, metadata, file listing, size-checked download.

Response shapes below were verified against live responses (see docs/NASA_DATA_SOURCES.md):
  catalogue  GET /biodata/api/v2/datasets/            -> {"OSD-1": {"REST_URL": ...}, ...}
  detail     GET /biodata/api/v2/dataset/OSD-n/        -> {"OSD-n": {"REST_URL","assays","files","metadata":{lowercase keys}}}
  files      GET /biodata/api/v2/dataset/OSD-n/files/  -> {"OSD-n": {"files": {name: {"REST_URL","URL"}}}}
  search     GET osdr.nasa.gov/osdr/data/search?term=..&from=..&size=..&type=cgene -> Elasticsearch {"hits": {"total", "hits":[{"_source":{...}}]}}
"""
import re
import time
from pathlib import Path

from . import labels
from .http import NasaError, NasaHTTP, iso_now, redact

V2 = "https://visualization.osdr.nasa.gov/biodata/api/v2"
LEGACY = "https://osdr.nasa.gov/osdr/data"
STUDY_PAGE = "https://osdr.nasa.gov/bio/repo/data/studies/{acc}"
ACC_RE = re.compile(r"^OSD-\d{1,5}$")
EXTERNAL_RE = re.compile(r"^(GSE\d+|GSM\d+|PRJ[NED][A-Z]\d+|PXD\d+|mgm[\d.]+|SRP\d+|ERP\d+|MTBLS\d+|ST\d{6})$", re.I)

# Body-system topics: search terms are plain words understood by the OSDR search index.
TOPICS = {
    "cardiovascular": ["cardiovascular", "heart", "vascular"],
    "bone": ["bone", "osteoclast", "skeletal"],
    "muscle": ["muscle atrophy", "skeletal muscle", "soleus"],
    "immune": ["immune", "inflammation", "astronaut blood"],
    "radiation": ["radiation", "cosmic", "irradiation"],
    "sleep": ["circadian", "sleep"],
    "vision": ["retina", "ocular", "optic nerve"],
    "neurological": ["brain", "neuro", "cognitive"],
    "respiratory": ["lung", "pulmonary", "respiratory"],
    "renal": ["kidney", "renal"],
    "human spaceflight": ["astronaut", "human spaceflight", "crew"],
}

TABULAR = {".csv", ".tsv", ".txt", ".json", ".xlsx", ".xls"}
SPECIALIZED = {  # extension -> (format name, suggested parser)
    ".fastq.gz": ("FASTQ sequencing reads", "FastQC / Biopython SeqIO / nf-core pipelines"),
    ".fq.gz": ("FASTQ sequencing reads", "FastQC / Biopython SeqIO"),
    ".bam": ("aligned sequencing reads (BAM)", "samtools / pysam"),
    ".sam": ("aligned sequencing reads (SAM)", "samtools / pysam"),
    ".cram": ("aligned sequencing reads (CRAM)", "samtools"),
    ".cel": ("Affymetrix CEL microarray", "R: oligo / affy"),
    ".idat": ("Illumina IDAT methylation array", "R: minfi / sesame"),
    ".mzml": ("mass spectrometry (mzML)", "pyteomics / OpenMS"),
    ".raw": ("instrument raw data", "vendor tools / ThermoRawFileParser"),
    ".fasta": ("FASTA sequences", "Biopython SeqIO"), ".fa": ("FASTA sequences", "Biopython SeqIO"),
    ".vcf": ("variant calls (VCF)", "cyvcf2 / pysam"), ".bed": ("genomic intervals (BED)", "pybedtools"),
    ".bw": ("BigWig coverage", "pyBigWig"), ".h5": ("HDF5 container", "h5py"),
    ".rds": ("R data object", "R: readRDS"), ".rdata": ("R data object", "R: load"),
    ".tar.gz": ("compressed archive", "tarfile"), ".tgz": ("compressed archive", "tarfile"),
    ".pdf": ("PDF document", "pdfplumber"), ".png": ("image", "Pillow"), ".jpg": ("image", "Pillow"), ".html": ("HTML report", "browser"),
}


def valid_osdr_accession(acc: str) -> bool:
    return bool(ACC_RE.match(acc or ""))


def classify_file(name: str) -> dict:
    n = name.lower()
    for ext in sorted(SPECIALIZED, key=len, reverse=True):
        if n.endswith(ext):
            f, parser = SPECIALIZED[ext]
            return {"kind": "specialized", "format": f, "parser": parser, "processable": False}
    if n.endswith(".zip"):
        return {"kind": "archive", "format": "ZIP archive", "parser": "zipfile (ISA-Tab metadata is tab-separated text)", "processable": True}
    ext = Path(n).suffix
    if ext in TABULAR:
        return {"kind": "tabular", "format": ext.lstrip(".").upper(), "parser": "pandas", "processable": True}
    return {"kind": "unknown", "format": ext or "no extension", "parser": None, "processable": False}


def _date(v):
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(float(v)))
    except (TypeError, ValueError):
        return str(v) if v else None


def normalize_hit(hit: dict) -> dict:
    s = hit.get("_source", {})
    acc = s.get("Accession") or ""
    organism = (s.get("organism") or "").strip()
    ext = (s.get("Data Source Accession") or "").strip()
    return {
        "accession": acc if valid_osdr_accession(acc) else None,
        "glds": s.get("Identifiers"), "title": s.get("Study Title"), "organism": organism,
        "human": "homo sapiens" in organism.lower(), "material_type": s.get("Material Type"),
        "assay": s.get("Study Assay Measurement Type"), "technology": s.get("Study Assay Technology Type"),
        "project_type": s.get("Project Type"), "mission": (s.get("Mission") or {}).get("Name") or None,
        "flight_program": s.get("Flight Program") or None,
        "description": (s.get("Study Description") or "")[:600], "publication": s.get("Study Publication Title") or None,
        "external_accession": ext or None,
        "external_note": "Referenced in an external repository (for example GEO). This is not an OSDR accession." if ext else None,
        "release_date": _date(s.get("Study Public Release Date")),
        "source_url": STUDY_PAGE.format(acc=acc) if valid_osdr_accession(acc) else None,
        "rest_url": f"{V2}/dataset/{acc}/" if valid_osdr_accession(acc) else None,
        "label": "NASA_RESEARCH",
    }


class OSDR:
    def __init__(self, http: NasaHTTP, prov: labels.Provenance):
        self.http, self.prov = http, prov

    def catalogue(self):
        data, meta = self.http.get_json(f"{V2}/datasets/", ttl=24 * 3600)
        accs = sorted((k for k in data if valid_osdr_accession(k)), key=lambda a: int(a.split("-")[1]))
        return {"accessions": accs, "count": len(accs), "meta": meta}

    def search(self, term="spaceflight", offset=0, size=25, human_only=False, dtype="cgene"):
        size = max(1, min(int(size), 100))
        fetch_size = 100 if human_only else size
        data, meta = self.http.get_json(f"{LEGACY}/search", {"term": term, "from": int(offset), "size": fetch_size, "type": dtype}, ttl=1800)
        hits = data.get("hits", {})
        items = [normalize_hit(h) for h in hits.get("hits", [])]
        if human_only:
            items = [i for i in items if i["human"]][:size]
        for i in items:
            if i["accession"]:
                self.prov.record("NASA_RESEARCH", "OSDR", i["accession"], i["title"] or "", {"organism": i["organism"], "assay": i["assay"], "mission": i["mission"]},
                                 source_url=i["source_url"] or "", status="discovered")
        total = hits.get("total")
        total = total.get("value") if isinstance(total, dict) else total
        return {"term": term, "total_matches": total, "returned": len(items), "human_only": human_only, "items": items, "meta": meta}

    def metadata(self, acc):
        if not valid_osdr_accession(acc):
            raise NasaError(f"'{acc}' is not an OSDR accession (expected OSD-<number>). GEO, PRIDE and MG-RAST ids are different repositories.")
        data, meta = self.http.get_json(f"{V2}/dataset/{acc}/", ttl=6 * 3600)
        body = data.get(acc) or {}
        md = body.get("metadata", {})
        return {"accession": acc, "title": md.get("study title"), "organism": md.get("organism"), "material_type": md.get("material type"),
                "assay": md.get("study assay measurement type"), "technology": md.get("study assay technology type"),
                "mission": (md.get("mission") or {}).get("name") or None, "project_type": md.get("project type"),
                "description": md.get("study description"), "external_accession": md.get("data source accession") or None,
                "glds": md.get("identifiers"), "release_date": _date(md.get("study public release date")),
                "factors": md.get("study factor name"), "files_url": (body.get("files") or {}).get("REST_URL"),
                "source_url": STUDY_PAGE.format(acc=acc), "label": "NASA_RESEARCH", "meta": meta, "raw_metadata": md}

    def files(self, acc):
        if not valid_osdr_accession(acc):
            raise NasaError(f"'{acc}' is not an OSDR accession")
        data, meta = self.http.get_json(f"{V2}/dataset/{acc}/files/", ttl=6 * 3600)
        files = (data.get(acc) or {}).get("files", {})
        out = []
        for name, v in files.items():
            c = classify_file(name)
            out.append({"name": name, "download_url": v.get("URL"), "rest_url": v.get("REST_URL"), **c})
        out.sort(key=lambda f: (not f["processable"], f["name"]))
        return {"accession": acc, "count": len(out), "processable": sum(1 for f in out if f["processable"]), "files": out, "meta": meta}

    def download_and_process(self, acc, filename, max_mb=25):
        from . import process
        listing = self.files(acc)
        entry = next((f for f in listing["files"] if f["name"] == filename), None)
        if not entry or not entry["download_url"]:
            raise NasaError(f"{filename} is not in the file listing of {acc}")  # only listed files can be fetched
        if not entry["processable"]:
            status = {"accession": acc, "file": filename, "status": "unsupported_format", "format": entry["format"], "suggested_parser": entry["parser"],
                      "note": "Not downloaded: specialized scientific format that this pipeline does not parse as CSV."}
            self.prov.record("NASA_RESEARCH", "OSDR", f"{acc}/{filename}", filename, status, source_url=entry["download_url"], status="unsupported_format")
            return status
        limit = int(max_mb * 1e6)
        size, _ = self.http.head_size(entry["download_url"])
        if size is not None and size > limit:
            st = {"accession": acc, "file": filename, "status": "skipped_too_large", "size_mb": round(size / 1e6, 1), "limit_mb": max_mb}
            self.prov.record("NASA_RESEARCH", "OSDR", f"{acc}/{filename}", filename, st, source_url=entry["download_url"], status="skipped_too_large")
            return st
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
        raw = labels.NASA_DIR / "raw" / acc / safe
        dl = self.http.download(entry["download_url"], raw, limit)
        md = self.metadata(acc)
        report = process.process_file(raw, acc=acc, title=md.get("title"), source_url=entry["download_url"], download=dl, organism=md.get("organism"))
        self.prov.record("NASA_RESEARCH", "OSDR", f"{acc}/{filename}", md.get("title") or filename,
                         {"organism": md.get("organism"), "tables": [t["name"] for t in report.get("tables", [])], "usable_records": report.get("usable_records")},
                         units=report.get("units", {}), source_url=entry["download_url"], status=report["status"], local_path=str(raw))
        return report
