"""NASA Technical Reports Server (NTRS OpenAPI), Human Research Roadmap risk pages, and the Environmental Data App.
NTRS: documented OpenAPI at https://ntrs.nasa.gov/api/openapi/ (root https://ntrs.nasa.gov/api, path /citations/search, parameter q).
Response fields are parsed defensively because they were not verified live here.
EDA: the page documents telemetry and radiation tables per mission, but the data endpoint was not visible in the page text.
No endpoint is guessed: set EDA_API_BASE only after confirming it in the EDA 'API' section."""
import os
import re
from urllib.parse import urljoin

from . import labels
from .http import NasaError, NasaHTTP, iso_now

NTRS = "https://ntrs.nasa.gov/api"
HRR = "https://humanresearchroadmap.nasa.gov/risks/"
EDA = "https://visualization.osdr.nasa.gov/eda/"
MISSION_RE = re.compile(r"\b(RR-\d+|APEX-\d+(?:-\d+)?|VEG-\d+[A-Z]?)\b")


class Research:
    def __init__(self, http: NasaHTTP, prov: labels.Provenance):
        self.http, self.prov = http, prov

    def ntrs_search(self, q, size=10):
        data, meta = self.http.get_json(f"{NTRS}/citations/search", {"q": q, "page.size": max(1, min(int(size), 25))}, ttl=3600)
        res = data.get("results") if isinstance(data, dict) else None
        if res is None:
            raise NasaError(f"unexpected NTRS response shape (keys: {list(data)[:8] if isinstance(data, dict) else type(data).__name__})", meta["status"], meta["final_url"])
        items = []
        for r in res[:size]:
            nid = r.get("id")
            items.append({"id": nid, "title": r.get("title"), "abstract": (r.get("abstract") or "")[:700], "type": r.get("stiType"),
                          "created": r.get("created") or r.get("distributionDate"), "keywords": r.get("keywords", []),
                          "url": f"https://ntrs.nasa.gov/citations/{nid}" if nid else None, "label": "NASA_RESEARCH"})
            if nid:
                self.prov.record("NASA_RESEARCH", "NTRS", nid, r.get("title") or "", {"type": r.get("stiType")}, source_url=items[-1]["url"], status="retrieved")
        total = (data.get("stats") or {}).get("total") if isinstance(data.get("stats"), dict) else None
        return {"query": q, "total": total, "returned": len(items), "items": items, "meta": meta}

    def hrr_risks(self):
        html, meta = self.http.get_text(HRR)
        found = {}
        for href, text in re.findall(r'<a[^>]+href=["\']([^"\']*(?:/risks/|/Risks/)[^"\']+)["\'][^>]*>(.*?)</a>', html, re.S | re.I):
            t = re.sub(r"<[^>]+>|\s+", " ", text).strip()
            if 6 < len(t) < 140:
                found[urljoin(HRR, href)] = t
        items = [{"title": t, "url": u, "label": "NASA_RESEARCH"} for u, t in found.items()][:60]
        return {"returned": len(items), "items": items, "meta": meta,
                "note": "Titles and links scraped from the public page. Open each link for the official evidence report." if items else "No risk links found in the page HTML (it may load them with JavaScript). Open the page directly."}

    def eda_discover(self):
        base_env = os.environ.get("EDA_API_BASE", "").strip()
        html, meta = self.http.get_text(EDA)
        missions = sorted(set(MISSION_RE.findall(html)), key=lambda m: (m.split("-")[0], m))
        cands = sorted({urljoin(EDA, h) for h in re.findall(r'href=["\']([^"\']+)["\']', html) if re.search(r"api|download|\.csv|\.json|\.xlsx", h, re.I)})
        status = "NASA_OBSERVED" if (base_env or cands) else "UNAVAILABLE"
        rec = {"page": EDA, "missions_listed": missions, "documented_data_tabs": ["Telemetry Data", "Radiation Data", "Summary Table", "Telemetry Table", "Radiation Table"],
               "parameters_documented": ["temperature", "relative humidity", "CO2", "radiation (GCR, SAA, total, accumulated)"],
               "api_candidates_in_page": cands, "configured_api_base": base_env or None, "label": status, "meta": meta,
               "note": ("Endpoint candidates found in the page; verify before use." if cands else
                        "The page lists missions, telemetry and radiation tables for download, but no data endpoint appears in its HTML. "
                        "Open the 'API' section on the page, confirm the documented URL, then set EDA_API_BASE in .env. Nothing is guessed.")}
        self.prov.record(status, "NASA EDA", "discovery", "Environmental Data App", {"missions": missions, "candidates": cands}, source_url=EDA, status="discovered" if status != "UNAVAILABLE" else "endpoint_not_exposed")
        return rec
