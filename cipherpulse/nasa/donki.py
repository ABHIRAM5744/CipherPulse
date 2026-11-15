"""NASA DONKI space-weather events. These are recorded solar/space-weather events, NOT individual astronaut radiation doses.
Endpoints and parameters confirmed from NASA CCMC DONKI documentation: startDate/endDate (default last 30 days), notifications type=all|FLR|SEP|CME|IPS|MPC|GST|RBE|report."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import labels
from .http import NasaError, NasaHTTP, iso_now

BASE = "https://api.nasa.gov/DONKI"
TYPES = {"FLR": "Solar flare", "CME": "Coronal mass ejection", "SEP": "Solar energetic particle event", "GST": "Geomagnetic storm",
         "RBE": "Radiation belt enhancement", "IPS": "Interplanetary shock", "MPC": "Magnetopause crossing", "HSS": "High-speed solar wind stream",
         "notifications": "DONKI notification"}
ID_KEYS = ["flrID", "activityID", "sepID", "gstID", "rbeID", "mpcID", "hssID", "messageID"]
TIME_KEYS = ["peakTime", "beginTime", "startTime", "eventTime", "messageIssueTime"]
NOTE = "Recorded space-weather event. Not a measurement of any astronaut's radiation dose."


def api_key():
    k = os.environ.get("NASA_API_KEY", "").strip()
    return (k, "configured") if k else ("DEMO_KEY", "DEMO_KEY: rate-limited (about 30 requests/hour). Get a free key at https://api.nasa.gov/ and set NASA_API_KEY in .env")


def _first(d, keys):
    return next((d[k] for k in keys if d.get(k)), None)


def summarize(kind, e):
    if kind == "FLR":
        return f"Class {e.get('classType', '?')} flare" + (f" from {e['sourceLocation']}" if e.get("sourceLocation") else "")
    if kind == "GST":
        kps = [k.get("kpIndex") for k in e.get("allKpIndex", []) if isinstance(k.get("kpIndex"), (int, float))]
        return f"Geomagnetic storm, peak Kp {max(kps)}" if kps else "Geomagnetic storm"
    if kind == "CME":
        return (e.get("note") or "Coronal mass ejection")[:160] or "Coronal mass ejection"
    if kind == "IPS":
        return f"Interplanetary shock at {e.get('location', 'unknown location')}"
    if kind == "notifications":
        return f"{e.get('messageType', 'Notification')}: {(e.get('messageBody') or '')[:140].strip()}"
    return TYPES.get(kind, kind)


def normalize(kind, e):
    return {"type": kind, "type_name": TYPES.get(kind, kind), "id": _first(e, ID_KEYS), "time": _first(e, TIME_KEYS), "summary": summarize(kind, e),
            "link": e.get("link") or e.get("messageURL"), "label": "NASA_OBSERVED", "source": "NASA DONKI", "note": NOTE, "raw": e}


class Donki:
    def __init__(self, http: NasaHTTP, prov: labels.Provenance):
        self.http, self.prov = http, prov

    def _one(self, kind, start, end, key):
        params = {"startDate": start, "endDate": end, "api_key": key}
        if kind == "notifications":
            params["type"] = "all"
        try:
            data, meta = self.http.get_json(f"{BASE}/{kind}", params, ttl=900)
        except NasaError as e:
            return {"type": kind, "error": str(e), "status": e.status, "label": "UNAVAILABLE", "events": []}
        if not isinstance(data, list):
            return {"type": kind, "error": f"unexpected response shape: {type(data).__name__}", "label": "UNAVAILABLE", "events": [], "meta": meta}
        events = [normalize(kind, e) for e in data if isinstance(e, dict)]
        for ev in events:
            self.prov.record("NASA_OBSERVED", f"DONKI/{kind}", ev["id"] or ev["time"] or "?", ev["summary"], {"time": ev["time"], "type": kind},
                             source_url=meta["final_url"], status="retrieved")
        return {"type": kind, "count": len(events), "events": events, "meta": meta, "label": "NASA_OBSERVED"}

    def events(self, types=("FLR", "CME", "SEP", "GST"), days=30):
        key, key_status = api_key()
        days = max(1, min(int(days), 365))
        end = datetime.now(timezone.utc).date()
        start, end_s = (end - timedelta(days=days)).isoformat(), end.isoformat()
        types = [t for t in types if t in TYPES]
        with ThreadPoolExecutor(max_workers=4) as ex:
            res = list(ex.map(lambda t: self._one(t, start, end_s, key), types))
        flat = sorted((e for r in res for e in r["events"]), key=lambda e: e["time"] or "", reverse=True)
        return {"start": start, "end": end_s, "key_status": key_status, "by_type": {r["type"]: {k: v for k, v in r.items() if k != "events"} for r in res},
                "events": flat, "count": len(flat), "retrieved_at": iso_now(), "label": "NASA_OBSERVED", "note": NOTE}
