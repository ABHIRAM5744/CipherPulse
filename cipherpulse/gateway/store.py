"""Encrypted, hash-chained vault (SQLite) + rejected-packet log + alerts."""
import json
import sqlite3
import threading
import time

from .. import config
from ..security import crypto


class Vault:
    def __init__(self, path=None):
        self.db = sqlite3.connect(path or config.DB_PATH, check_same_thread=False)
        self.lock = threading.Lock()
        self.key = crypto.master_key()
        self._tamper_backup = None
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS records(
              id INTEGER PRIMARY KEY AUTOINCREMENT, astro TEXT, seq INTEGER, ts TEXT,
              enc TEXT, prev_hash TEXT, hash TEXT);
            CREATE TABLE IF NOT EXISTS rejected(
              id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, astro TEXT, reason TEXT, raw TEXT);
            CREATE TABLE IF NOT EXISTS alerts(
              id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, astro TEXT, kind TEXT,
              severity TEXT, data TEXT);
            """
        )
        self.db.commit()

    # ---- records ----
    def last_hash(self):
        r = self.db.execute("SELECT hash FROM records ORDER BY id DESC LIMIT 1").fetchone()
        return r[0] if r else crypto.GENESIS

    def last_seqs(self):
        return {a: s for a, s in self.db.execute("SELECT astro, MAX(seq) FROM records GROUP BY astro")}

    @staticmethod
    def _meta(astro, seq, ts):
        return f"{astro}:{seq}:{ts}"

    def append(self, pkt: dict) -> str:
        astro, seq, ts = pkt["astronaut_id"], pkt["seq"], pkt["ts"]
        meta = self._meta(astro, seq, ts)
        with self.lock:
            prev = self.last_hash()
            enc = crypto.encrypt(self.key, crypto.canonical(pkt), meta.encode())
            h = crypto.chain_hash(prev, enc, meta)
            self.db.execute(
                "INSERT INTO records(astro,seq,ts,enc,prev_hash,hash) VALUES(?,?,?,?,?,?)",
                (astro, seq, ts, enc, prev, h),
            )
            self.db.commit()
        return h

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM records").fetchone()[0]

    def history(self, astro, limit=60):
        rows = self.db.execute(
            "SELECT enc, astro, seq, ts FROM records WHERE astro=? ORDER BY id DESC LIMIT ?",
            (astro, limit),
        ).fetchall()
        out = []
        for enc, a, s, t in rows:
            try:
                p = json.loads(crypto.decrypt(self.key, enc, self._meta(a, s, t).encode()))
                out.append({"ts": p["ts"], "seq": p["seq"], "vitals": p["vitals"]})
            except Exception:
                out.append({"ts": t, "seq": s, "error": "undecryptable (tampered)"})
        return list(reversed(out))

    def alert_stats(self):
        rows = self.db.execute("SELECT kind, severity, COUNT(*) FROM alerts GROUP BY kind, severity").fetchall()
        return [{"kind": k, "severity": sv, "count": n} for k, sv, n in rows]

    def verify_chain(self):
        """Re-walk the whole chain. Detects edits, deletions and re-ordering."""
        with self.lock:
            rows = self.db.execute(
                "SELECT id,astro,seq,ts,enc,prev_hash,hash FROM records ORDER BY id"
            ).fetchall()
        prev = crypto.GENESIS
        for rid, a, s, t, enc, ph, h in rows:
            meta = self._meta(a, s, t)
            if ph != prev:
                return {"ok": False, "checked": len(rows), "broken_at": rid, "reason": "link broken (record removed or re-ordered)"}
            if crypto.chain_hash(ph, enc, meta) != h:
                return {"ok": False, "checked": len(rows), "broken_at": rid, "reason": "hash mismatch (record modified)"}
            try:
                crypto.decrypt(self.key, enc, meta.encode())
            except Exception:
                return {"ok": False, "checked": len(rows), "broken_at": rid, "reason": "authentication failed (ciphertext altered)"}
            prev = h
        return {"ok": True, "checked": len(rows), "broken_at": None, "reason": "all records intact"}

    # ---- attacker simulation (demo only) ----
    def tamper_demo(self):
        with self.lock:
            r = self.db.execute("SELECT id, enc FROM records ORDER BY id DESC LIMIT 1 OFFSET 5").fetchone()
            if not r:
                return None
            self._tamper_backup = r
            bad = r[1][:-4] + ("AAAA" if not r[1].endswith("AAAA") else "BBBB")
            self.db.execute("UPDATE records SET enc=? WHERE id=?", (bad, r[0]))
            self.db.commit()
            return r[0]

    def tamper_restore(self):
        with self.lock:
            if not self._tamper_backup:
                return False
            rid, enc = self._tamper_backup
            self.db.execute("UPDATE records SET enc=? WHERE id=?", (enc, rid))
            self.db.commit()
            self._tamper_backup = None
            return True

    # ---- rejects / alerts ----
    def reject(self, astro, reason, raw):
        with self.lock:
            self.db.execute("INSERT INTO rejected(at,astro,reason,raw) VALUES(?,?,?,?)",
                            (time.time(), astro, reason, json.dumps(raw)[:2000]))
            self.db.commit()

    def save_alert(self, astro, kind, severity, data) -> int:
        with self.lock:
            cur = self.db.execute("INSERT INTO alerts(at,astro,kind,severity,data) VALUES(?,?,?,?,?)",
                                  (time.time(), astro, kind, severity, json.dumps(data)))
            self.db.commit()
            return cur.lastrowid

    def update_alert(self, aid, data):
        with self.lock:
            self.db.execute("UPDATE alerts SET data=? WHERE id=?", (json.dumps(data), aid))
            self.db.commit()

    def recent_alerts(self, limit=30):
        rows = self.db.execute("SELECT id,at,astro,kind,severity,data FROM alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": i, "at": at, "astro": a, "kind": k, "severity": s, **json.loads(d)} for i, at, a, k, s, d in rows]
