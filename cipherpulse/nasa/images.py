"""NASA Image and Video Library. Search/asset/metadata endpoints per the official API docs; search shape verified live."""
from . import labels
from .http import NasaError, NasaHTTP

BASE = "https://images-api.nasa.gov"


def normalize_item(it):
    d = (it.get("data") or [{}])[0]
    links = {}
    for l in it.get("links", []):
        href = l.get("href", "")
        for tag in ("thumb", "small", "medium", "large", "orig"):
            if f"~{tag}." in href:
                links[tag] = {"url": href, "width": l.get("width"), "height": l.get("height"), "bytes": l.get("size")}
    nid = d.get("nasa_id")
    return {"nasa_id": nid, "title": d.get("title"), "description": (d.get("description") or "")[:500], "center": d.get("center"),
            "date_created": d.get("date_created"), "keywords": d.get("keywords", []), "credit": d.get("photographer") or "NASA",
            "images": links, "thumb": (links.get("thumb") or links.get("small") or {}).get("url"),
            "page_url": f"https://images.nasa.gov/details/{nid}" if nid else None, "manifest_url": it.get("href"),
            "label": "NASA_OBSERVED", "note": "NASA photograph or media asset. Check NASA media usage guidelines before redistribution."}


class Images:
    def __init__(self, http: NasaHTTP, prov: labels.Provenance):
        self.http, self.prov = http, prov

    def search(self, q, page=1, page_size=20, year_start=None):
        params = {"q": q, "media_type": "image", "page": max(1, int(page)), "page_size": max(1, min(int(page_size), 50))}
        if year_start:
            params["year_start"] = str(year_start)
        data, meta = self.http.get_json(f"{BASE}/search", params, ttl=3600)
        col = data.get("collection", {})
        items = [normalize_item(i) for i in col.get("items", [])]
        for i in items:
            if i["nasa_id"]:
                self.prov.record("NASA_OBSERVED", "NASA Image Library", i["nasa_id"], i["title"] or "", {"center": i["center"], "credit": i["credit"]},
                                 source_url=i["page_url"] or "", status="retrieved")
        return {"query": q, "returned": len(items), "total_hits": (col.get("metadata") or {}).get("total_hits"), "items": items, "meta": meta}

    def asset(self, nasa_id):
        data, meta = self.http.get_json(f"{BASE}/asset/{nasa_id}", ttl=86400)
        urls = [i.get("href") for i in (data.get("collection", {}).get("items") or []) if i.get("href")]
        return {"nasa_id": nasa_id, "asset_urls": urls, "meta": meta}

    def metadata(self, nasa_id):
        data, meta = self.http.get_json(f"{BASE}/metadata/{nasa_id}", ttl=86400)
        return {"nasa_id": nasa_id, "response": data, "meta": meta}
