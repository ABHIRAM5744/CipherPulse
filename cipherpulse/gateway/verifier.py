"""Gatekeeper: signature, replay, freshness and physical-plausibility checks."""
from datetime import datetime, timezone

from ..security import crypto

PLAUSIBLE = {
    "hr": (20, 250), "spo2": (50, 100), "temp": (30, 43),
    "resp": (3, 60), "radiation": (0, 1000),
}
FRESH_LIVE_S = 30
FRESH_BUFFERED_S = 24 * 3600


class Verifier:
    def __init__(self, registry: dict, last_seqs: dict):
        self.registry = registry
        self.last_seq = dict(last_seqs)

    def check(self, pkt: dict):
        """Return (ok, reason)."""
        try:
            astro = pkt["astronaut_id"]
            sig = pkt["signature"]
            body = {k: v for k, v in pkt.items() if k != "signature"}
            seq, vitals = int(pkt["seq"]), pkt["vitals"]
            ts = datetime.fromisoformat(pkt["ts"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError, AttributeError):
            return False, "malformed packet"
        pub = self.registry.get(astro)
        if not pub:
            return False, "unknown device"
        if not crypto.verify(pub, body, sig):
            return False, "bad signature (forged or modified)"
        if seq <= self.last_seq.get(astro, 0):
            return False, "replay (sequence already seen)"
        age = abs((datetime.now(timezone.utc) - ts).total_seconds())
        if age > (FRESH_BUFFERED_S if pkt.get("buffered") else FRESH_LIVE_S):
            return False, "stale timestamp"
        for k, (lo, hi) in PLAUSIBLE.items():
            v = vitals.get(k)
            if not isinstance(v, (int, float)) or not (lo <= v <= hi):
                return False, f"implausible {k}={v}"
        return True, "ok"

    def accept(self, pkt):
        self.last_seq[pkt["astronaut_id"]] = int(pkt["seq"])
