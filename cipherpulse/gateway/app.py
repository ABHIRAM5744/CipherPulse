"""CipherPulse gateway: verify -> vault -> detect -> explain -> broadcast, all live."""
import asyncio
import csv
import html
import io
import json
import re
import time
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import config
from ..agents import a2a, graph, llm
from ..analysis import detector as det
from ..analysis.detector import Detector
from ..security import crypto
from .store import Vault
from .verifier import Verifier
from ..nasa.api import router as nasa_router

WEB = Path(__file__).resolve().parent.parent / "web"
ST = {}  # runtime state, filled in lifespan
DOSE_BUDGET_USV = 2000.0  # illustrative mission budget; simulation clock: 1 real second = 1 simulated hour


def now():
    return time.time()


def reject_type(reason: str) -> str:
    r = reason.lower()
    if "signature" in r:
        return "forged_or_modified"
    if "replay" in r:
        return "replay"
    if "implausible" in r:
        return "sensor_fault"
    if "stale" in r:
        return "stale"
    if "unknown" in r:
        return "unknown_device"
    return "malformed"


async def broadcast(msg: dict):
    dead = []
    for ws in list(ST["dash"]):
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:
            dead.append(ws)
    for ws in dead:
        ST["dash"].discard(ws)


@asynccontextmanager
async def lifespan(app):
    vault = Vault()
    a2a.CARD["url"] = f"http://localhost:{config.PORT}/a2a"
    ST.update(
        vault=vault,
        verifier=Verifier(crypto.registry(config.CREW), vault.last_seqs()),
        detector=Detector(),
        dash=set(), sensors=set(),
        crew={a: {"status": "ok", "kind": "normal", "vitals": None, "ts": None, "buffered": False, "index": 100} for a in config.CREW},
        counts={"accepted": 0, "rejected": 0, "buffered": 0},
        rtypes=Counter(), dose={a: 0.0 for a in config.CREW}, phase="orbit",
        cool={}, last_reject={}, link_up=True, t0=now(),
    )
    print(f"[gateway] ready · agents={graph.ENGINE} · llm={llm.available() or 'rules-only'} · memory={graph.memory.backend}", flush=True)
    yield


app = FastAPI(title="CipherPulse", lifespan=lifespan)
app.include_router(nasa_router)
ORIGIN = "SIMULATED_DEMO"  # all live vitals come from the demo simulator


# --------------------------------------------------------------------------- pipeline
async def handle_packet(pkt: dict):
    ok, reason = ST["verifier"].check(pkt)
    astro = pkt.get("astronaut_id", "?") if isinstance(pkt, dict) else "?"
    if not ok:
        ST["counts"]["rejected"] += 1
        rt = reject_type(reason)
        ST["rtypes"][rt] += 1
        ST["vault"].reject(astro, reason, pkt)
        entry = {"type": "reject", "astro": astro, "reason": reason, "rtype": rt, "ts": now(),
                 "counts": ST["counts"], "rtypes": dict(ST["rtypes"])}
        ST["last_reject"] = entry
        await broadcast(entry)
        key = (astro, rt)
        if now() - ST["cool"].get(key, 0) > 6:
            ST["cool"][key] = now()
            data = {"explanation": f"Blocked a packet claiming to be {astro}: {reason}. It was not stored and not shown as health data.",
                    "actions": ["Review the rejected-packet log", "Re-provision the device key if this repeats"],
                    "provider": "rules", "engine": "gateway"}
            aid = ST["vault"].save_alert(astro, "security", "critical", data)
            await broadcast({"type": "alert", "id": aid, "astro": astro, "kind": "security", "severity": "critical", "at": now(), **data})
        return

    ST["verifier"].accept(pkt)
    h = ST["vault"].append(pkt)
    ST["counts"]["accepted"] += 1
    if pkt.get("buffered"):
        ST["counts"]["buffered"] += 1
    v = pkt["vitals"]
    f = ST["detector"].update(astro, v, ST["phase"])
    ST["dose"][astro] = ST["dose"].get(astro, 0.0) + float(v["radiation"])  # 1 packet = 1 s = 1 simulated hour
    c = ST["crew"][astro]
    c.update(status=f.severity, kind=f.kind, vitals=v, ts=pkt["ts"], buffered=bool(pkt.get("buffered")), index=f.index)
    await broadcast({"type": "vitals", "astro": astro, "vitals": v, "status": f.severity, "kind": f.kind,
                     "ts": pkt["ts"], "buffered": bool(pkt.get("buffered")), "hash": h[:10], "ml": f.ml_score,
                     "index": f.index, "dose": round(ST["dose"][astro], 1), "counts": ST["counts"], "origin": ORIGIN})

    # after a phase change vitals need ~15 s to settle: hold back non-critical alerts so transitions do not cause noise
    if f.severity != "ok" and (f.severity == "critical" or now() - ST.get("phase_at", 0) > 15):
        key = (astro, f.kind)
        gap = 12 if f.severity == "critical" else 30
        if now() - ST["cool"].get(key, 0) > gap:
            ST["cool"][key] = now()
            finding = {"severity": f.severity, "kind": f.kind, "reasons": f.reasons, "eta_s": f.eta, "phase": ST["phase"]}
            aid = ST["vault"].save_alert(astro, f.kind, f.severity, {"explanation": "Agents are analysing…", "actions": [], "vitals": v})
            await broadcast({"type": "alert", "id": aid, "astro": astro, "kind": f.kind, "severity": f.severity,
                             "at": now(), "explanation": "Agents are analysing…", "actions": [], "vitals": v, "eta": f.eta})
            asyncio.create_task(run_agent(aid, astro, v, finding))


async def run_agent(aid, astro, v, finding):
    try:
        out = await graph.explain(astro, v, finding)
    except Exception as e:  # never let the agent break the live pipeline
        out = {"explanation": f"Agent error: {type(e).__name__}", "actions": [], "provider": "none", "engine": "error"}
    out["vitals"] = v
    ST["vault"].update_alert(aid, out)
    await broadcast({"type": "agent", "id": aid, "astro": astro, "kind": finding["kind"],
                     "severity": finding["severity"], **out})


# --------------------------------------------------------------------------- websockets
@app.websocket("/ws/sensor")
async def ws_sensor(ws: WebSocket):
    await ws.accept()
    ST["sensors"].add(ws)
    if ST["phase"] != "orbit":
        await ws.send_text(json.dumps({"cmd": "phase", "name": ST["phase"]}))
    try:
        while True:
            m = json.loads(await ws.receive_text())
            if "event" in m:
                if m["event"] == "link":
                    ST["link_up"] = m["up"]
                    await broadcast({"type": "link", "up": m["up"], "queued": m.get("queued", 0)})
                continue
            await handle_packet(m)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[gateway] sensor socket error: {e!r}", flush=True)
    finally:
        ST["sensors"].discard(ws)


@app.websocket("/ws/dashboard")
async def ws_dash(ws: WebSocket):
    await ws.accept()
    ST["dash"].add(ws)
    await ws.send_text(json.dumps({"type": "snapshot", **snapshot()}))
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ST["dash"].discard(ws)


# --------------------------------------------------------------------------- REST
def snapshot():
    return {"crew": ST["crew"], "counts": ST["counts"], "link_up": ST["link_up"],
            "records": ST["vault"].count(), "sensors_online": len(ST["sensors"]),
            "uptime": int(now() - ST["t0"]), "alerts": ST["vault"].recent_alerts(15),
            "origin": ORIGIN, "phase": ST["phase"], "phases": list(det.PHASES), "dose": {a: round(x, 1) for a, x in ST["dose"].items()},
            "dose_budget": DOSE_BUDGET_USV, "rtypes": dict(ST["rtypes"]),
            "limits": det.LIMITS, "defaults": det.DEFAULT_LIMITS,
            "agents": {"engine": graph.ENGINE, "llm": llm.available() or ["rules"], "memory": graph.memory.backend}}


@app.get("/api/state")
async def api_state():
    return snapshot()


@app.get("/api/alerts")
async def api_alerts():
    return ST["vault"].recent_alerts(50)


@app.get("/api/history/{astro}")
async def api_history(astro: str):
    return ST["vault"].history(astro)


@app.get("/api/export/{astro}.csv")
async def api_export(astro: str):
    rows = await asyncio.to_thread(ST["vault"].history, astro, 5000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "seq", "heart_rate_bpm", "spo2_percent", "temperature_c", "breathing_per_min", "radiation_uSv_per_h", "data_origin"])
    for r in rows:
        v = r.get("vitals") or {}
        w.writerow([r["ts"], r["seq"], v.get("hr"), v.get("spo2"), v.get("temp"), v.get("resp"), v.get("radiation"), ORIGIN])
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="cipherpulse_{astro}.csv"'})


@app.post("/api/integrity/verify")
async def api_verify():
    res = await asyncio.to_thread(ST["vault"].verify_chain)
    await broadcast({"type": "integrity", **res})
    return res


@app.post("/api/phase")
async def api_phase(req: Request):
    name = (await req.json()).get("name")
    if name not in det.PHASES:
        return JSONResponse({"error": "unknown phase", "phases": list(det.PHASES)}, status_code=400)
    ST["phase"] = name
    ST["phase_at"] = now()
    await send_sensors({"cmd": "phase", "name": name})
    await broadcast({"type": "phase", "name": name})
    return {"phase": name}


@app.get("/api/limits")
async def api_limits():
    return {"limits": det.LIMITS, "defaults": det.DEFAULT_LIMITS}


@app.post("/api/limits")
async def api_limits_set(req: Request):
    body = await req.json()
    lim = det.reset_limits() if body.get("reset") else det.set_limits({k: v for k, v in (body.get("limits") or {}).items()})
    await broadcast({"type": "limits", "limits": lim})
    return {"limits": lim}


async def send_sensors(cmd: dict):
    for ws in list(ST["sensors"]):
        try:
            await ws.send_text(json.dumps(cmd))
        except Exception:
            ST["sensors"].discard(ws)
    return bool(ST["sensors"])


@app.post("/api/control")
async def api_control(req: Request):
    m = await req.json()
    cmd = m.get("cmd")
    if cmd == "tamper":
        rid = ST["vault"].tamper_demo()
        res = await asyncio.to_thread(ST["vault"].verify_chain)
        await broadcast({"type": "integrity", **res, "tampered": rid})
        return {"tampered_record": rid, **res}
    if cmd == "restore":
        okk = ST["vault"].tamper_restore()
        res = await asyncio.to_thread(ST["vault"].verify_chain)
        await broadcast({"type": "integrity", **res})
        return {"restored": okk, **res}
    if cmd in ("scenario", "link", "spoof"):
        return {"sent": await send_sensors(m)}
    return JSONResponse({"error": "unknown cmd"}, status_code=400)


def at_risk():
    return sorted(((a, c["index"], c["status"]) for a, c in ST["crew"].items() if c["vitals"]), key=lambda t: t[1])


def context_text():
    lines = [f"Mission phase: {ST['phase']}."]
    for a, c in ST["crew"].items():
        v = c["vitals"]
        if v:
            lines.append(f"{a}: {c['status']} ({c['kind']}), health index {c['index']}, hr {v['hr']}, spo2 {v['spo2']}, temp {v['temp']}, resp {v['resp']}, radiation {v['radiation']}, dose {ST['dose'][a]:.0f} of {DOSE_BUDGET_USV:.0f} uSv budget")
    lines.append(f"Link to Earth: {'up' if ST['link_up'] else 'DOWN (buffering)'}. Packets accepted {ST['counts']['accepted']}, blocked {ST['counts']['rejected']} ({dict(ST['rtypes'])}).")
    lines += [f"Alert {x['astro']} {x['kind']}: {x.get('explanation','')}" for x in ST["vault"].recent_alerts(3)]
    return "\n".join(lines)


def rule_answer(q: str) -> str:
    ql = q.lower()
    if re.search(r"risk|worst|lowest|who needs|most", ql):
        rk = at_risk()
        if not rk:
            return "No data yet."
        a, idx, stt = rk[0]
        return f"{a} has the lowest health index at {idx} out of 100 and is {stt}."
    if re.search(r"dose|radiation budget|exposure", ql):
        a, d = max(ST["dose"].items(), key=lambda t: t[1])
        return f"Highest radiation dose is {a} with {d:.0f} of {DOSE_BUDGET_USV:.0f} micro-sieverts, {d / DOSE_BUDGET_USV * 100:.0f} percent of the demo budget."
    m = re.search(r"\ba[1-9]\b", ql)
    if m and m.group(0).upper() in ST["crew"]:
        a = m.group(0).upper()
        c = ST["crew"][a]
        v = c["vitals"]
        if not v:
            return f"No data from {a} yet."
        return f"{a} is {c['status']} with health index {c['index']}. Heart rate {v['hr']}, oxygen {v['spo2']} percent, temperature {v['temp']}, breathing {v['resp']}."
    bad = [a for a, c in ST["crew"].items() if c["status"] != "ok"]
    base = "All crew vitals are normal." if not bad else f"Attention: {', '.join(bad)} outside normal range."
    return f"{base} {ST['counts']['rejected']} packets were blocked so far."


@app.post("/api/chat")
async def api_chat(req: Request):
    q = (await req.json()).get("text", "").strip()
    ql = q.lower()
    if re.search(r"verify|integrity|tamper.?proof|check the chain", ql):
        r = await api_verify()
        return {"reply": f"Integrity check complete. {r['checked']} records checked. {r['reason']}.", "provider": "tool"}
    m = re.search(r"(exercise|co2|radiation|fever|sleep)", ql)
    a = re.search(r"\ba[1-9]\b", ql)
    if m and a and re.search(r"simulate|trigger|run|start", ql):
        await send_sensors({"cmd": "scenario", "astro": a.group(0).upper(), "name": m.group(1)})
        return {"reply": f"Started the {m.group(1)} scenario on {a.group(0).upper()}.", "provider": "tool"}
    ph = re.search(r"phase.*(launch|orbit|eva|sleep)|(launch|eva|spacewalk) mode", ql)
    if ph:
        name = next(g for g in ph.groups() if g)
        name = "eva" if name == "spacewalk" else name
        await api_phase(_Fake(None, {"name": name}))
        return {"reply": f"Mission phase set to {name}. Alert limits adjusted for that phase.", "provider": "tool"}
    if re.search(r"(link|connection).*(down|lost|cut)|blackout", ql):
        await send_sensors({"cmd": "link", "up": False})
        return {"reply": "Link to Earth cut. Wearables are now buffering locally.", "provider": "tool"}
    if re.search(r"(link|connection).*(up|restor|back)", ql):
        await send_sensors({"cmd": "link", "up": True})
        return {"reply": "Link restored. Buffered readings are syncing in order.", "provider": "tool"}
    try:
        text, provider = await graph.chat(q, context_text())
        return {"reply": text, "provider": provider}
    except Exception:
        return {"reply": rule_answer(q), "provider": "rules"}


# --------------------------------------------------------------------------- mission report
@app.get("/api/report", response_class=HTMLResponse)
async def api_report():
    chain = await asyncio.to_thread(ST["vault"].verify_chain)
    e = html.escape
    try:
        summary, who = await graph.chat("Write a 3 sentence executive summary of this mission session for a flight director.", context_text())
    except Exception:
        rk = at_risk()
        summary = (f"{len(ST['crew'])} crew monitored in phase {ST['phase']}. "
                   f"{ST['counts']['accepted']} packets verified and {ST['counts']['rejected']} blocked. "
                   f"Lowest health index: {rk[0][0]} at {rk[0][1]}." if rk else "No crew data yet.")
        who = "rules"
    crew_rows = "".join(
        f"<tr><td>{e(a)}</td><td>{e(c['status'])}</td><td>{c['index']}</td>"
        f"<td>{('%s bpm, %s%% O2, %s C' % (c['vitals']['hr'], c['vitals']['spo2'], c['vitals']['temp'])) if c['vitals'] else '-'}</td>"
        f"<td>{ST['dose'][a]:.0f} / {DOSE_BUDGET_USV:.0f} uSv</td></tr>" for a, c in ST["crew"].items())
    alert_rows = "".join(
        f"<tr class='{e(x['severity'])}'><td>{e(x['astro'])}</td><td>{e(x['kind'])}</td><td>{e(x['severity'])}</td><td>{e(str(x.get('explanation','')))}</td></tr>"
        for x in ST["vault"].recent_alerts(12))
    rt = "".join(f"<li>{e(k.replace('_', ' '))}: {v}</li>" for k, v in ST["rtypes"].items()) or "<li>none</li>"
    ok = chain["ok"]
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>CipherPulse mission report</title>
<style>body{{font:15px/1.5 "Segoe UI",system-ui,sans-serif;max-width:860px;margin:32px auto;padding:0 20px;color:#14232b}}
h1{{font-size:26px;margin-bottom:4px}}h2{{margin-top:28px;border-bottom:2px solid #7fe9ff;padding-bottom:4px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border:1px solid #cfe3ea;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#eaf7fb}}tr.critical td{{background:#ffecee}}tr.warning td{{background:#fff6e5}}
.ok{{color:#0a7d4f;font-weight:600}}.bad{{color:#c0243a;font-weight:600}}small{{color:#5b7683}}
@media print{{body{{margin:0}}}}</style></head><body>
<h1>CipherPulse mission report</h1><small>Generated {time.strftime('%Y-%m-%d %H:%M:%S')} · vitals are SIMULATED_DEMO (not real astronaut telemetry) · NASA research data is labelled separately · prototype, not a medical device</small>
<h2>Executive summary</h2><p>{e(summary)}</p><small>Written by: {e(who)}</small>
<h2>Crew status</h2><table><tr><th>Crew</th><th>Status</th><th>Health index</th><th>Latest vitals</th><th>Radiation dose</th></tr>{crew_rows}</table>
<h2>Data integrity</h2><p class="{'ok' if ok else 'bad'}">{'Hash chain intact' if ok else 'Hash chain BROKEN'}: {chain['checked']} records checked. {e(chain['reason'])}.</p>
<h2>Security events</h2><p>Packets verified: {ST['counts']['accepted']}. Packets blocked: {ST['counts']['rejected']}.</p><ul>{rt}</ul>
<h2>Recent alerts</h2><table><tr><th>Crew</th><th>Type</th><th>Severity</th><th>AI explanation</th></tr>{alert_rows or '<tr><td colspan=4>No alerts</td></tr>'}</table>
<h2>Method</h2><p>Signed Ed25519 packets, AES-256-GCM encrypted vault with SHA-256 hash chain, phase-aware limits, Isolation Forest, trend forecasting, LangGraph agent explanations. Mission phase: {e(ST['phase'])}. Simulation clock: 1 real second = 1 simulated hour.</p>
<p><small>Tip: press Ctrl+P and choose Save as PDF.</small></p></body></html>"""
    return HTMLResponse(doc)


# --------------------------------------------------------------------------- A2A
@app.get("/.well-known/agent.json")
async def agent_card():
    return a2a.CARD


@app.post("/a2a")
async def a2a_rpc(req: Request):
    body = await req.json()
    if body.get("method") not in ("message/send", "tasks/send"):
        return {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32601, "message": "method not found"}}
    text = a2a.extract_text(body.get("params", {}))
    r = await api_chat(_Fake(text))
    return a2a.wrap_reply(body.get("id"), r["reply"])


class _Fake:
    def __init__(self, t, payload=None):
        self.t, self.payload = t, payload

    async def json(self):
        return self.payload if self.payload is not None else {"text": self.t}


# --------------------------------------------------------------------------- UI
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
async def index():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})
