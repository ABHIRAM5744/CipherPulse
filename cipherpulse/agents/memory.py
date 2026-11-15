"""Long-term crew memory. Local SQLite by default; Mem0 platform if MEM0_API_KEY is set."""
import sqlite3
import threading
import time

from .. import config


class CrewMemory:
    def __init__(self):
        self.db = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.execute("CREATE TABLE IF NOT EXISTS memory(id INTEGER PRIMARY KEY, at REAL, astro TEXT, text TEXT)")
        self.db.commit()
        self.mem0 = None
        if config.get("MEM0_API_KEY"):
            try:
                from mem0 import MemoryClient  # pip install mem0ai
                self.mem0 = MemoryClient(api_key=config.get("MEM0_API_KEY"))
            except Exception as e:
                print(f"[memory] Mem0 unavailable ({e!r}); using local memory", flush=True)

    @property
    def backend(self):
        return "mem0+local" if self.mem0 else "local"

    def add(self, astro, text):
        with self.lock:
            self.db.execute("INSERT INTO memory(at,astro,text) VALUES(?,?,?)", (time.time(), astro, text))
            self.db.commit()
        if self.mem0:
            try:
                self.mem0.add([{"role": "user", "content": text}], user_id=astro)
            except Exception:
                pass

    def recall(self, astro, k=3):
        rows = self.db.execute("SELECT at,text FROM memory WHERE astro=? ORDER BY id DESC LIMIT ?", (astro, k)).fetchall()
        out = [f"{int(time.time()-at)}s ago: {t}" for at, t in rows]
        if self.mem0 and not out:
            try:
                res = self.mem0.search("recent health events", user_id=astro)
                out = [r.get("memory", "") for r in (res if isinstance(res, list) else res.get("results", []))][:k]
            except Exception:
                pass
        return out
