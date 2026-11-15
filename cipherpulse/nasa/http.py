"""One HTTP client for every NASA source: timeouts, retries with backoff, Retry-After, disk cache, size-checked downloads."""
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx

from . import labels

CACHE = labels.NASA_DIR / "cache"
UA = "CipherPulse/2.0 (NASA Space Apps hackathon; contact via project README)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class NasaError(Exception):
    def __init__(self, message, status=None, url=""):
        super().__init__(message)
        self.status, self.url = status, url


def redact(url: str) -> str:
    return re.sub(r"(api_key=)[^&]+", r"\1***", url)


def iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class NasaHTTP:
    def __init__(self, transport=None, sleep=time.sleep, cache_dir: Path = CACHE):
        self.client = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True,
                                   headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*"}, transport=transport)
        self.sleep, self.cache_dir = sleep, cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ---- low level -------------------------------------------------------------
    def _request(self, method, url, params=None, retries=3, **kw):
        last = None
        for attempt in range(retries + 1):
            try:
                r = self.client.request(method, url, params=params, **kw)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = NasaError(f"network error: {type(e).__name__}: {e}", None, url)
            else:
                if r.status_code in RETRY_STATUS and attempt < retries:
                    wait = min(30.0, float(r.headers.get("Retry-After", 2 ** attempt)) if str(r.headers.get("Retry-After", "")).replace(".", "").isdigit() else 2 ** attempt)
                    last = NasaError(f"HTTP {r.status_code}", r.status_code, url)
                    self.sleep(wait)
                    continue
                return r
            if attempt < retries:
                self.sleep(2 ** attempt)
        raise last

    # ---- JSON with cache ---------------------------------------------------------
    def get_json(self, url, params=None, ttl=3600, retries=3):
        """Returns (data, meta). meta has status, final_url (key redacted), retrieved_at, from_cache, stale, rate_remaining."""
        key = hashlib.sha256((url + "?" + urlencode(sorted((params or {}).items()))).encode()).hexdigest()[:40]
        f = self.cache_dir / f"{key}.json"
        if ttl and f.exists() and time.time() - f.stat().st_mtime < ttl:
            c = json.loads(f.read_text())
            c["meta"]["from_cache"] = True
            return c["data"], c["meta"]
        try:
            r = self._request("GET", url, params=params, retries=retries)
            if r.status_code >= 400:
                raise NasaError(f"HTTP {r.status_code}: {r.text[:200]}", r.status_code, redact(str(r.url)))
            try:
                data = r.json()
            except ValueError:
                raise NasaError(f"response was not JSON (content-type {r.headers.get('content-type')})", r.status_code, redact(str(r.url)))
            meta = {"status": r.status_code, "final_url": redact(str(r.url)), "retrieved_at": iso_now(), "from_cache": False,
                    "stale": False, "rate_remaining": r.headers.get("X-RateLimit-Remaining")}
            f.write_text(json.dumps({"data": data, "meta": meta}))
            return data, meta
        except NasaError:
            if f.exists():  # serve stale cache rather than fail the dashboard
                c = json.loads(f.read_text())
                c["meta"].update(from_cache=True, stale=True)
                return c["data"], c["meta"]
            raise

    def get_text(self, url, params=None):
        r = self._request("GET", url, params=params)
        if r.status_code >= 400:
            raise NasaError(f"HTTP {r.status_code}", r.status_code, redact(str(r.url)))
        return r.text, {"status": r.status_code, "final_url": redact(str(r.url)), "retrieved_at": iso_now()}

    # ---- files -----------------------------------------------------------------
    def head_size(self, url):
        """Size in bytes if the server tells us, else None. Never downloads the body."""
        host = urlparse(url).hostname or ""
        if not host.endswith(".nasa.gov"):
            raise NasaError("refusing non-nasa.gov host", None, url)
        try:
            r = self._request("HEAD", url, retries=1)
            if r.status_code < 400 and r.headers.get("content-length"):
                return int(r.headers["content-length"]), r.status_code
        except NasaError:
            pass
        with self.client.stream("GET", url) as r:  # headers only; body is not read
            cl = r.headers.get("content-length")
            return (int(cl) if cl and cl.isdigit() else None), r.status_code

    def download(self, url, dest: Path, max_bytes: int):
        host = urlparse(url).hostname or ""
        if not host.endswith(".nasa.gov"):
            raise NasaError("refusing non-nasa.gov host", None, url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        h, n = hashlib.sha256(), 0
        with self.client.stream("GET", url) as r:
            if r.status_code >= 400:
                raise NasaError(f"HTTP {r.status_code}", r.status_code, url)
            cl = r.headers.get("content-length")
            if cl and cl.isdigit() and int(cl) > max_bytes:
                raise NasaError(f"file is {int(cl)/1e6:.1f} MB, over the {max_bytes/1e6:.0f} MB limit", r.status_code, url)
            with open(dest, "wb") as out:
                for chunk in r.iter_bytes(65536):
                    n += len(chunk)
                    if n > max_bytes:
                        out.close(); dest.unlink(missing_ok=True)
                        raise NasaError("download exceeded the size limit and was stopped", r.status_code, url)
                    h.update(chunk); out.write(chunk)
            return {"bytes": n, "sha256": h.hexdigest(), "content_type": r.headers.get("content-type"),
                    "final_url": str(r.url), "status": r.status_code}
