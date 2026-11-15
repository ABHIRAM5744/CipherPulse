"""Run the NASA integrations for real and report honestly. Run from the project folder:  python scripts/validate_nasa.py
HTTP 200 alone is NOT treated as success. Each source has explicit success criteria, and failures are explained."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cipherpulse import config  # noqa: E402  (loads .env)
from cipherpulse.nasa import labels  # noqa: E402
from cipherpulse.nasa.donki import Donki, api_key  # noqa: E402
from cipherpulse.nasa.http import NasaError, NasaHTTP  # noqa: E402
from cipherpulse.nasa.images import Images  # noqa: E402
from cipherpulse.nasa.osdr import OSDR  # noqa: E402
from cipherpulse.nasa.research import Research  # noqa: E402

http, prov = NasaHTTP(), labels.Provenance()
report = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sources": {}}


def step(name, fn):
    t0 = time.time()
    try:
        out = fn()
        out.setdefault("ok", True)
    except NasaError as e:
        out = {"ok": False, "error": str(e), "http_status": e.status, "url": e.url}
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out["seconds"] = round(time.time() - t0, 1)
    report["sources"][name] = out
    print(f"\n[{'PASS' if out['ok'] else 'FAIL'}] {name} ({out['seconds']}s)")
    for k, v in out.items():
        if k not in ("ok", "seconds"):
            print(f"    {k}: {json.dumps(v, default=str)[:300]}")
    return out


def osdr_check():
    o = OSDR(http, prov)
    cat = o.catalogue()
    res = o.search("astronaut", 0, 25, human_only=True)
    humans = [i for i in res["items"] if i["accession"]]
    if not humans:
        return {"ok": False, "error": "no human OSDR studies returned for 'astronaut'", "catalogue_count": cat["count"]}
    chosen, fl = None, None
    for h in humans[:8]:  # prefer a dataset that has something we can actually parse
        f = o.files(h["accession"])
        if f["processable"]:
            chosen, fl = h, f
            break
        chosen, fl = chosen or h, fl or f
    acc = chosen["accession"]
    out = {"endpoint_catalogue": cat["meta"]["final_url"], "http_status": cat["meta"]["status"], "catalogue_count": cat["count"],
           "search_total_matches": res["total_matches"], "human_datasets_found": [(h["accession"], h["title"][:60]) for h in humans[:5]],
           "chosen": {"accession": acc, "title": chosen["title"], "organism": chosen["organism"], "external_accession_not_osdr": chosen["external_accession"]},
           "files_discovered": fl["count"], "files_processable": fl["processable"],
           "formats": sorted({f["format"] for f in fl["files"]})}
    target = next((f for f in fl["files"] if f["processable"]), None)
    if not target:
        out.update(ok=False, error="dataset has no tabular/archive files to download; only specialized formats", sample_files=[f["name"] for f in fl["files"][:5]])
        return out
    rep = o.download_and_process(acc, target["name"], float(__import__("os").environ.get("NASA_MAX_DOWNLOAD_MB", "25")))
    out["downloaded_file"] = target["name"]
    out["download"] = rep.get("download")
    out["processing_status"] = rep.get("status")
    out["tables"] = [{"name": t["name"], "rows": t["rows"], "columns": t["columns"][:8], "units": t["units"], "missing_cols": len(t["missing"])} for t in rep.get("tables", [])]
    out["usable_records"] = rep.get("usable_records")
    out["ok"] = rep.get("status") == "processed" and bool(rep.get("tables")) and rep.get("usable_records", 0) >= 0 and rep["tables"][0]["rows"] > 0
    if not out["ok"]:
        out["error"] = rep.get("error") or rep.get("note") or rep.get("status")
    return out


def donki_check():
    key, ks = api_key()
    r = Donki(http, prov).events(("FLR", "CME", "SEP", "GST"), 30)
    types_ok = {t: v.get("count") for t, v in r["by_type"].items() if "error" not in v}
    errs = {t: v["error"] for t, v in r["by_type"].items() if "error" in v}
    return {"ok": bool(types_ok), "key_status": ks, "event_counts": types_ok, "errors": errs, "total_events": r["count"],
            "note": "valid but empty responses are reported as zero events, not as failures" if r["count"] == 0 and types_ok else None,
            "sample": [(e["type"], e["id"], e["summary"]) for e in r["events"][:3]]}


def images_check():
    r = Images(http, prov).search("astronaut health", 1, 10)
    good = [i for i in r["items"] if i["nasa_id"] and i["images"]]
    return {"ok": len(good) > 0, "returned": r["returned"], "with_image_urls": len(good), "sample": [(i["nasa_id"], i["title"][:50], i["credit"]) for i in good[:3]]}


def ntrs_check():
    r = Research(http, prov).ntrs_search("spaceflight bone loss astronaut", 5)
    return {"ok": r["returned"] > 0, "returned": r["returned"], "total": r["total"], "sample": [(i["id"], (i["title"] or "")[:60]) for i in r["items"][:3]]}


def hrr_check():
    r = Research(http, prov).hrr_risks()
    return {"ok": r["returned"] > 0, "returned": r["returned"], "sample": [i["title"] for i in r["items"][:5]], "note": r["note"]}


def eda_check():
    r = Research(http, prov).eda_discover()
    return {"ok": bool(r["missions_listed"]), "missions_listed": r["missions_listed"][:10], "data_endpoint": "FOUND" if r["api_candidates_in_page"] or r["configured_api_base"] else "UNAVAILABLE",
            "api_candidates_in_page": r["api_candidates_in_page"][:5], "note": r["note"]}


for n, f in [("OSDR", osdr_check), ("DONKI", donki_check), ("NASA Image Library", images_check), ("NTRS", ntrs_check), ("Human Research Roadmap", hrr_check), ("EDA", eda_check)]:
    step(n, f)

report["record_counts"] = prov.counts()
out = labels.NASA_DIR / "validation_report.json"
out.write_text(json.dumps(report, indent=2, default=str))
print("\n" + "=" * 60)
for n, v in report["sources"].items():
    print(f"  {'PASS' if v['ok'] else 'FAIL':5} {n}")
print(f"\nFull report: {out}\nRecords stored by label: {report['record_counts']}")
sys.exit(0 if all(v["ok"] for v in report["sources"].values()) else 1)
