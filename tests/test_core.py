import copy
from datetime import datetime, timezone

from cipherpulse.analysis.detector import Detector
from cipherpulse.gateway.store import Vault
from cipherpulse.gateway.verifier import Verifier
from cipherpulse.security import crypto
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def packet(priv, seq, hr=70, buffered=False, astro="T1"):
    b = {"astronaut_id": astro, "seq": seq, "ts": now(), "buffered": buffered,
         "vitals": {"hr": hr, "spo2": 98, "temp": 36.6, "resp": 14, "radiation": 0.3}}
    b["signature"] = crypto.sign(priv, b)
    return b


def make():
    k = Ed25519PrivateKey.generate()
    return k, Verifier({"T1": crypto.public_b64(k)}, {})


def test_valid_packet_accepted():
    k, v = make()
    assert v.check(packet(k, 1)) == (True, "ok")


def test_forged_signature_rejected():
    _, v = make()
    ok, why = v.check(packet(Ed25519PrivateKey.generate(), 1))
    assert not ok and "signature" in why


def test_modified_vitals_rejected():
    k, v = make()
    p = packet(k, 1); p["vitals"]["hr"] = 31
    assert not v.check(p)[0]


def test_replay_rejected():
    k, v = make()
    p = packet(k, 5)
    assert v.check(p)[0]; v.accept(p)
    ok, why = v.check(copy.deepcopy(p))
    assert not ok and "replay" in why


def test_implausible_value_rejected():
    k, v = make()
    ok, why = v.check(packet(k, 1, hr=0))
    assert not ok and "implausible" in why


def test_hash_chain_detects_tamper(tmp_path):
    k = Ed25519PrivateKey.generate()
    vault = Vault(str(tmp_path / "t.db"))
    for i in range(1, 9):
        vault.append(packet(k, i))
    assert vault.verify_chain()["ok"]
    vault.db.execute("UPDATE records SET enc = substr(enc,1,length(enc)-4) || 'AAAA' WHERE id=4")
    res = vault.verify_chain()
    assert not res["ok"] and res["broken_at"] == 4


def test_hash_chain_detects_deleted_record(tmp_path):
    k = Ed25519PrivateKey.generate()
    vault = Vault(str(tmp_path / "t.db"))
    for i in range(1, 9):
        vault.append(packet(k, i))
    vault.db.execute("DELETE FROM records WHERE id=3")
    assert not vault.verify_chain()["ok"]


def test_detector_flags_air_quality():
    d = Detector()
    for _ in range(60):
        d.update("T1", {"hr": 66, "spo2": 98, "temp": 36.6, "resp": 14, "radiation": 0.3})
    f = d.update("T1", {"hr": 98, "spo2": 91, "temp": 36.7, "resp": 25, "radiation": 0.3})
    assert f.severity in ("warning", "critical") and f.kind == "air_quality"


def test_detector_quiet_on_normal():
    d = Detector()
    for _ in range(80):
        f = d.update("T1", {"hr": 66, "spo2": 98, "temp": 36.6, "resp": 14, "radiation": 0.3})
    assert f.severity == "ok"


# ---- v2 features -----------------------------------------------------------
NORMAL = {"hr": 66, "spo2": 98, "temp": 36.6, "resp": 14, "radiation": 0.3}


def test_forecast_gives_early_warning_before_limit():
    d = Detector()
    for _ in range(50):
        d.update("T1", dict(NORMAL))
    f = None
    for i in range(1, 33):  # SpO2 sliding 0.12 per second, still above the 94 limit for a while
        f = d.update("T1", {**NORMAL, "spo2": 98 - 0.12 * i})
        if f.kind == "trend_spo2":
            break
    assert f.kind == "trend_spo2" and f.severity == "warning" and f.eta and f.eta <= 45


def test_health_index_drops_with_bad_vitals():
    d = Detector()
    good = d.update("T1", dict(NORMAL)).index
    for _ in range(8):
        bad = d.update("T2", {"hr": 120, "spo2": 88, "temp": 38.6, "resp": 28, "radiation": 0.3}).index
    assert good >= 95 and bad < 60


def test_phase_relaxes_exertion_limits():
    d = Detector()
    v = {"hr": 120, "spo2": 98, "temp": 37.2, "resp": 26, "radiation": 0.3}
    assert d.update("T1", v, "orbit").severity != "ok"
    assert d.update("T3", v, "eva").severity == "ok"


def test_limits_editable_and_resettable():
    from cipherpulse.analysis import detector as det
    det.set_limits({"hr": [55, 100, 40, 140]})
    assert det.LIMITS["hr"][1] == 100
    det.reset_limits()
    assert det.LIMITS["hr"][1] == 105


def test_api_report_csv_phase(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from cipherpulse import config
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "api.db"))
    from cipherpulse.gateway.app import app
    with TestClient(app) as c:
        assert c.get("/api/state").json()["phase"] == "orbit"
        assert c.post("/api/phase", json={"name": "eva"}).json()["phase"] == "eva"
        assert c.post("/api/phase", json={"name": "mars"}).status_code == 400
        r = c.get("/api/report")
        assert r.status_code == 200 and "mission report" in r.text
        assert c.get("/api/export/A1.csv").text.startswith("timestamp,seq")
        assert c.get("/").status_code == 200
        assert c.get("/.well-known/agent.json").json()["name"].startswith("CipherPulse")
