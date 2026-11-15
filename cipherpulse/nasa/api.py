"""FastAPI router: exposes retrieved NASA data to the console. Keys stay on the server."""
import asyncio
import os

from fastapi import APIRouter, HTTPException, Query, Request

from . import labels, organs
from .donki import Donki, TYPES as DONKI_TYPES, api_key
from .http import NasaError, NasaHTTP
from .images import Images
from .osdr import OSDR, TOPICS, valid_osdr_accession
from .research import Research

router = APIRouter(prefix="/api/nasa", tags=["nasa"])
_S = {}


def svc():
    if not _S:
        http, prov = NasaHTTP(), labels.Provenance()
        _S.update(http=http, prov=prov, osdr=OSDR(http, prov), donki=Donki(http, prov), images=Images(http, prov), research=Research(http, prov))
    return _S


def reset_services(http=None):
    """Tests inject a client with a mock transport."""
    _S.clear()
    if http is not None:
        prov = labels.Provenance()
        _S.update(http=http, prov=prov, osdr=OSDR(http, prov), donki=Donki(http, prov), images=Images(http, prov), research=Research(http, prov))


async def run(fn, *a, **kw):
    try:
        return await asyncio.to_thread(fn, *a, **kw)
    except NasaError as e:
        raise HTTPException(status_code=502 if (e.status or 500) >= 500 or e.status is None else e.status,
                            detail={"error": str(e), "upstream_status": e.status, "label": "UNAVAILABLE", "url": e.url})


@router.get("/status")
async def status():
    s = svc()
    _, key_status = api_key()
    return {"label_definitions": labels.LABELS, "record_counts": s["prov"].counts(), "nasa_api_key": key_status,
            "sources": {"OSDR": "https://visualization.osdr.nasa.gov/biodata/api/", "DONKI": "https://api.nasa.gov/DONKI/", "Images": "https://images-api.nasa.gov",
                        "NTRS": "https://ntrs.nasa.gov/api/openapi/", "EDA": "https://visualization.osdr.nasa.gov/eda/", "HRR": "https://humanresearchroadmap.nasa.gov/risks/"},
            "topics": list(TOPICS), "organs": list(organs.ORGANS), "donki_types": list(DONKI_TYPES),
            "max_download_mb": float(os.environ.get("NASA_MAX_DOWNLOAD_MB", "25"))}


@router.get("/records")
async def records(label: str | None = None, source: str | None = None, limit: int = Query(200, le=1000)):
    return svc()["prov"].list(label, source, limit)


@router.get("/osdr/catalogue")
async def osdr_catalogue():
    return await run(svc()["osdr"].catalogue)


@router.get("/osdr/search")
async def osdr_search(q: str = "", topic: str | None = None, human: bool = False, size: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    term = q.strip() or (TOPICS[topic][0] if topic in TOPICS else "spaceflight")
    return await run(svc()["osdr"].search, term, offset, size, human)


@router.get("/osdr/{accession}")
async def osdr_dataset(accession: str):
    if not valid_osdr_accession(accession):
        raise HTTPException(400, {"error": "Not an OSDR accession. Expected OSD-<number>. GEO, PRIDE and MG-RAST ids belong to other repositories.", "label": "UNAVAILABLE"})
    s = svc()["osdr"]
    md, fl = await asyncio.gather(run(s.metadata, accession), run(s.files, accession))
    md.pop("raw_metadata", None)
    return {"metadata": md, "files": fl}


@router.post("/osdr/{accession}/download")
async def osdr_download(accession: str, request: Request):
    if not valid_osdr_accession(accession):
        raise HTTPException(400, {"error": "Not an OSDR accession", "label": "UNAVAILABLE"})
    body = await request.json()
    fname = body.get("file")
    if not fname:
        raise HTTPException(400, {"error": "file is required"})
    mx = min(float(body.get("max_mb", os.environ.get("NASA_MAX_DOWNLOAD_MB", "25"))), 200.0)
    return await run(svc()["osdr"].download_and_process, accession, fname, mx)


@router.get("/donki")
async def donki(types: str = "FLR,CME,SEP,GST", days: int = Query(30, ge=1, le=365)):
    return await run(svc()["donki"].events, tuple(t.strip() for t in types.split(",") if t.strip()), days)


@router.get("/images")
async def images(q: str = "astronaut health", page: int = 1, page_size: int = Query(20, le=50)):
    return await run(svc()["images"].search, q, page, page_size)


@router.get("/images/{nasa_id}")
async def image_asset(nasa_id: str):
    s = svc()["images"]
    a, m = await asyncio.gather(run(s.asset, nasa_id), run(s.metadata, nasa_id))
    return {"asset": a, "metadata": m}


@router.get("/ntrs")
async def ntrs(q: str, size: int = Query(10, le=25)):
    return await run(svc()["research"].ntrs_search, q, size)


@router.get("/hrr")
async def hrr():
    return await run(svc()["research"].hrr_risks)


@router.get("/eda")
async def eda():
    return await run(svc()["research"].eda_discover)


@router.get("/organ/{organ}")
async def organ(organ: str):
    cfg = organs.ORGANS.get(organ)
    if not cfg:
        raise HTTPException(404, {"error": "unknown organ", "known": list(organs.ORGANS)})
    s = svc()
    out = {"organ": organ, "system": cfg["system"], "limitations": organs.LIMITATIONS, "label": "NASA_RESEARCH"}

    async def safe(name, fn, *a):
        try:
            out[name] = await asyncio.to_thread(fn, *a)
        except NasaError as e:
            out[name] = {"error": str(e), "upstream_status": e.status, "label": "UNAVAILABLE"}

    terms = TOPICS[cfg["osdr"]]
    await asyncio.gather(
        safe("osdr_human", s["osdr"].search, terms[0] + " astronaut", 0, 6, True),
        safe("osdr_all", s["osdr"].search, terms[0], 0, 6, False),
        safe("ntrs", s["research"].ntrs_search, cfg["ntrs"], 6),
        safe("images", s["images"].search, cfg["images"], 1, 6),
    )
    return out
