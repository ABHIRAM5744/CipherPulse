"""NASA integration tests. Fixtures mirror the structure of REAL responses read from the live NASA APIs
(OSDR v2 detail/files, OSDR legacy search, NASA Image Library). DONKI fixtures follow NASA's documented event fields."""
import io
import json
import zipfile

import httpx
import pytest

from cipherpulse import config
from cipherpulse.nasa import labels, osdr, process
from cipherpulse.nasa.donki import Donki, api_key
from cipherpulse.nasa.http import NasaError, NasaHTTP
from cipherpulse.nasa.images import Images
from cipherpulse.nasa.research import Research

SEARCH = {"hits": {"total": 395, "hits": [
    {"_source": {"Accession": "OSD-483", "Identifiers": "GLDS-483", "Study Title": "small-RNA sequencing of sEV isolated from plasma of astronauts", "organism": "Homo sapiens",
                 "Material Type": "Peripheral Blood", "Study Assay Measurement Type": "transcription profiling", "Study Assay Technology Type": "RNA Sequencing (RNA-Seq)",
                 "Project Type": "Spaceflight Study", "Mission": {"Name": ""}, "Data Source Accession": "GSE193331", "Study Public Release Date": 1641945600,
                 "Study Description": "sEV miRNA in plasma of 14 astronauts"}},
    {"_source": {"Accession": "OSD-698", "Study Title": "Mouse brain frontal cortex", "organism": "Mus musculus", "Project Type": "Spaceflight Study",
                 "Mission": {"Name": "SpaceX-24"}, "Study Public Release Date": 1709510400.0}},
    {"_source": {"Accession": "not-an-osd", "Study Title": "odd", "organism": "Homo sapiens"}}]}}
DETAIL = {"OSD-483": {"REST_URL": "x", "files": {"REST_URL": "https://visualization.osdr.nasa.gov/biodata/api/v2/dataset/OSD-483/files/"},
                      "metadata": {"study title": "small-RNA sequencing of sEV isolated from plasma of astronauts", "organism": "Homo sapiens",
                                   "material type": "Peripheral Blood", "study assay measurement type": "transcription profiling", "mission": {"name": ""},
                                   "data source accession": "GSE193331", "identifiers": "GLDS-483", "study public release date": 1641945600}}}
DL = "https://osdr.nasa.gov/geode-py/ws/studies/OSD-483/download?source=datamanager&file="
FILES = {"OSD-483": {"files": {
    "GLDS-483_rna-seq_GSM5792297_raw.fastq.gz": {"REST_URL": "r1", "URL": DL + "GLDS-483_rna-seq_GSM5792297_raw.fastq.gz"},
    "OSD-483_metadata_GLDS-483-ISA.zip": {"REST_URL": "r2", "URL": DL + "OSD-483_metadata_GLDS-483-ISA.zip"}}}}
IMG = {"collection": {"items": [{"href": "https://images-assets.nasa.gov/image/iss058e003984/collection.json",
        "data": [{"center": "JSC", "date_created": "2019-01-16T00:00:00Z", "description": "Bio-Monitor smart shirt", "media_type": "image", "nasa_id": "iss058e003984",
                  "photographer": "David Saint-Jacques", "title": "Bio-Monitor"}],
        "links": [{"href": "https://images-assets.nasa.gov/image/iss058e003984/iss058e003984~thumb.jpg", "rel": "preview", "width": 640, "height": 426, "size": 64000},
                  {"href": "https://images-assets.nasa.gov/image/iss058e003984/iss058e003984~orig.jpg", "rel": "canonical", "width": 5568, "height": 3712, "size": 3670016}]}],
    "metadata": {"total_hits": 120}}}
FLR = [{"flrID": "2024-05-14T01:55:00-FLR-001", "peakTime": "2024-05-14T02:10Z", "classType": "X1.2", "sourceLocation": "S19W65", "link": "https://kauai.ccmc.gsfc.nasa.gov/DONKI/view/FLR/1"}]


def isa_zip():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("i_OSD-483.txt", "Study Title\tsmall-RNA of astronaut plasma\nStudy Description\tL-10, R-0, R+3\n")
        z.writestr("s_OSD-483.txt", "Source Name\tCharacteristics[Organism]\tAge (years)\tFactor Value[time]\nA01\tHomo sapiens\t45\tL-10\nA02\tHomo sapiens\t\tR+0\nA03\tHomo sapiens\t51\tR+3\n")
    return b.getvalue()


def handler(calls):
    def h(req: httpx.Request):
        calls.append((req.method, str(req.url)))
        u = str(req.url)
        if "osdr/data/search" in u:
            return httpx.Response(200, json=SEARCH)
        if u.endswith("/dataset/OSD-483/"):
            return httpx.Response(200, json=DETAIL)
        if u.endswith("/dataset/OSD-483/files/"):
            return httpx.Response(200, json=FILES)
        if "download?source=datamanager" in u and "ISA.zip" in u:
            return httpx.Response(200, content=isa_zip(), headers={"content-length": str(len(isa_zip())), "content-type": "application/zip"})
        if "images-api.nasa.gov/search" in u:
            return httpx.Response(200, json=IMG)
        if "api.nasa.gov/DONKI/FLR" in u:
            return httpx.Response(200, json=FLR)
        if "api.nasa.gov/DONKI/" in u:
            return httpx.Response(200, json=[])
        if u.startswith("https://visualization.osdr.nasa.gov/eda"):
            return httpx.Response(200, text="<html><li>RR-1</li><li>RR-3</li><li>APEX-03-1</li><li>VEG-01C</li></html>")
        return httpx.Response(404, text="nope")
    return h


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(labels, "NASA_DIR", tmp_path / "nasa")
    for d in ("raw", "processed", "metadata", "cache"):
        (tmp_path / "nasa" / d).mkdir(parents=True)
    calls = []
    http = NasaHTTP(transport=httpx.MockTransport(handler(calls)), sleep=lambda s: None, cache_dir=tmp_path / "cache")
    return http, labels.Provenance(str(tmp_path / "t.db")), calls


def test_accession_rules():
    assert osdr.valid_osdr_accession("OSD-483")
    assert not osdr.valid_osdr_accession("GSE193331")   # GEO is an external repository
    assert not osdr.valid_osdr_accession("PXD012345")   # PRIDE
    assert not osdr.valid_osdr_accession("../etc/passwd")


def test_classify_files():
    assert osdr.classify_file("x_raw.fastq.gz")["kind"] == "specialized" and not osdr.classify_file("x_raw.fastq.gz")["processable"]
    assert osdr.classify_file("ISA.zip")["processable"] and osdr.classify_file("a.csv")["kind"] == "tabular"
    assert osdr.classify_file("a.CEL")["parser"].startswith("R:")


def test_search_marks_human_and_external_ids(env):
    http, prov, _ = env
    r = osdr.OSDR(http, prov).search("spaceflight")
    first = r["items"][0]
    assert first["accession"] == "OSD-483" and first["human"] and first["external_accession"] == "GSE193331"
    assert "not an OSDR accession" in first["external_note"]
    assert r["items"][2]["accession"] is None            # malformed ids are never treated as OSDR accessions
    assert r["total_matches"] == 395
    assert [i["accession"] for i in osdr.OSDR(http, prov).search("x", human_only=True)["items"] if i["accession"]] == ["OSD-483"]


def test_files_listing_and_unsupported_not_downloaded(env):
    http, prov, calls = env
    o = osdr.OSDR(http, prov)
    fl = o.files("OSD-483")
    assert fl["count"] == 2 and fl["processable"] == 1
    out = o.download_and_process("OSD-483", "GLDS-483_rna-seq_GSM5792297_raw.fastq.gz")
    assert out["status"] == "unsupported_format" and "FastQC" in out["suggested_parser"]
    assert not any("download?source" in u for _, u in calls)   # nothing was downloaded


def test_download_and_process_isa_zip(env):
    http, prov, _ = env
    o = osdr.OSDR(http, prov)
    rep = o.download_and_process("OSD-483", "OSD-483_metadata_GLDS-483-ISA.zip")
    assert rep["status"] == "processed" and rep["source_url"].startswith(DL) and rep["label"] == "NASA_RESEARCH"
    t = rep["tables"][0]
    assert t["rows"] == 3 and "Age (years)" in t["columns"] and t["units"]["Age (years)"] == "years" and t["missing"]["Age (years)"] == 1
    assert t["numeric_summary"]["Age (years)"]["max"] == 51.0
    assert "Study Title" in rep["isa_investigation"]
    assert json.loads(open(rep["sidecar"]).read())["accession"] == "OSD-483"
    rec = prov.list(source="OSDR")
    assert any(r["status"] == "processed" and r["source_url"] for r in rec)


def test_csv_processing_units_and_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(labels, "NASA_DIR", tmp_path)
    for d in ("raw", "processed", "metadata"):
        (tmp_path / d).mkdir()
    f = tmp_path / "raw" / "vitals.csv"
    f.write_text("time,heart_rate (bpm),temp [C],note\n1,60,36.5,a\n2,,36.6,b\n3,64,,c\n")
    rep = process.process_file(f, "OSD-1")
    t = rep["tables"][0]
    assert t["units"] == {"heart_rate (bpm)": "bpm", "temp [C]": "C"} and t["missing"]["heart_rate (bpm)"] == 1 and rep["usable_records"] == 3


def test_download_size_limit_and_host_guard(env):
    http, _, _ = env
    with pytest.raises(NasaError):
        http.download("https://example.com/x.csv", http.cache_dir / "x", 100)
    with pytest.raises(NasaError):
        http.download(DL + "OSD-483_metadata_GLDS-483-ISA.zip", http.cache_dir / "x", 10)  # 10 byte cap


def test_retry_on_429_then_success(tmp_path):
    n = {"c": 0}
    def h(req):
        n["c"] += 1
        return httpx.Response(429, headers={"Retry-After": "1"}) if n["c"] < 3 else httpx.Response(200, json={"ok": 1})
    sleeps = []
    http = NasaHTTP(transport=httpx.MockTransport(h), sleep=sleeps.append, cache_dir=tmp_path)
    data, meta = http.get_json("https://api.nasa.gov/x", {"api_key": "SECRET"}, ttl=0)
    assert data == {"ok": 1} and n["c"] == 3 and len(sleeps) == 2 and "SECRET" not in meta["final_url"]


def test_stale_cache_served_when_nasa_down(tmp_path):
    ok = {"v": True}
    h = lambda req: httpx.Response(200, json={"a": 1}) if ok["v"] else httpx.Response(503)
    http = NasaHTTP(transport=httpx.MockTransport(h), sleep=lambda s: None, cache_dir=tmp_path)
    http.get_json("https://x.nasa.gov/a", ttl=1)
    ok["v"] = False
    import os, time as t
    for f in tmp_path.glob("*.json"):
        os.utime(f, (t.time() - 99, t.time() - 99))
    data, meta = http.get_json("https://x.nasa.gov/a", ttl=1, retries=0)
    assert data == {"a": 1} and meta["stale"]


def test_donki_labels_and_no_dose_confusion(env, monkeypatch):
    http, prov, _ = env
    monkeypatch.delenv("NASA_API_KEY", raising=False)
    assert api_key()[0] == "DEMO_KEY" and "api.nasa.gov" in api_key()[1]
    r = Donki(http, prov).events(("FLR", "CME"), 30)
    ev = r["events"][0]
    assert ev["label"] == "NASA_OBSERVED" and ev["id"].endswith("FLR-001") and "Class X1.2" in ev["summary"]
    assert "Not a measurement of any astronaut" in ev["note"] and "api_key=DEMO_KEY" not in json.dumps(r) and "api_key=***" in json.dumps(r["by_type"])
    assert all(rec["label"] == "NASA_OBSERVED" for rec in prov.list(source="DONKI/FLR"))


def test_images_normalized_with_credit(env):
    http, prov, _ = env
    r = Images(http, prov).search("astronaut health")
    i = r["items"][0]
    assert i["nasa_id"] == "iss058e003984" and i["credit"] == "David Saint-Jacques" and i["images"]["orig"]["bytes"] == 3670016 and i["page_url"].endswith(i["nasa_id"])


def test_eda_does_not_invent_endpoints(env, monkeypatch):
    http, prov, _ = env
    monkeypatch.delenv("EDA_API_BASE", raising=False)
    r = Research(http, prov).eda_discover()
    assert r["missions_listed"] == ["APEX-03-1", "RR-1", "RR-3", "VEG-01C"] and r["label"] == "UNAVAILABLE" and r["api_candidates_in_page"] == []


def test_router_end_to_end(env):
    from fastapi.testclient import TestClient
    from cipherpulse.gateway.app import app
    from cipherpulse.nasa import api
    http, _, _ = env
    api.reset_services(http)
    with TestClient(app) as c:
        assert c.get("/api/nasa/osdr/GSE193331").status_code == 400
        r = c.get("/api/nasa/osdr/search?topic=cardiovascular&human=true").json()
        assert r["items"][0]["accession"] == "OSD-483"
        d = c.get("/api/nasa/osdr/OSD-483").json()
        assert d["files"]["processable"] == 1 and d["metadata"]["organism"] == "Homo sapiens"
        assert c.get("/api/nasa/donki?types=FLR").json()["events"][0]["label"] == "NASA_OBSERVED"
        assert c.get("/api/nasa/images?q=x").json()["items"][0]["nasa_id"] == "iss058e003984"
        s = c.get("/api/nasa/status").json()
        assert "SIMULATED_DEMO" in s["label_definitions"] and s["record_counts"]
        assert c.get("/api/state").json()["origin"] == "SIMULATED_DEMO"
