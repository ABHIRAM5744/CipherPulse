"""Tiny .env loader + settings. No keys are ever hard-coded."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)


def _load_env():
    """Reads .env, then keys.env (a visible file name that is easy to drop into the folder). Real environment variables win."""
    for name in (".env", "keys.env"):
        f = ROOT / name
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()


def get(name, default=""):
    return os.environ.get(name, default)


HOST = get("CP_HOST", "127.0.0.1")
PORT = int(get("CP_PORT", "8000"))
CREW = [c.strip() for c in get("CP_CREW", "A1,A2,A3,A4").split(",") if c.strip()]
DB_PATH = str(DATA / "cipherpulse.db")
