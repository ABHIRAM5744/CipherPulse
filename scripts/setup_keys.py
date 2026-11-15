"""Enter your API keys once. They are saved only to the local .env file (git-ignored) and never leave your computer
except in requests to the matching service. Press Enter to keep a value or skip a key."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

KEYS = [
    ("NASA_API_KEY", "NASA API key (free at https://api.nasa.gov/)"),
    ("ANTHROPIC_API_KEY", "Claude / Anthropic API key"),
    ("GROQ_API_KEY", "Groq API key"),
    ("GEMINI_API_KEY", "Google Gemini API key"),
    ("MEM0_API_KEY", "Mem0 API key (optional)"),
]


def mask(v):
    return "not set" if not v else (v[:4] + "..." + v[-4:] if len(v) > 10 else "set")


def read_env(path: Path):
    lines = path.read_text().splitlines() if path.exists() else (ROOT / ".env.example").read_text().splitlines()
    vals = {}
    for ln in lines:
        if "=" in ln and not ln.lstrip().startswith("#"):
            k, v = ln.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return lines, vals


def write_env(path: Path, lines, updates):
    out, seen = [], set()
    for ln in lines:
        k = ln.split("=", 1)[0].strip() if "=" in ln and not ln.lstrip().startswith("#") else None
        if k in updates:
            out.append(f"{k}={updates[k]}"); seen.add(k)
        else:
            out.append(ln)
    out += [f"{k}={v}" for k, v in updates.items() if k not in seen]
    path.write_text("\n".join(out) + "\n")


def run(env_path: Path, ask=input, test_nasa=True, say=print):
    lines, cur = read_env(env_path)
    say("\nCipherPulse key setup. Press Enter to keep the current value or to skip.\n")
    updates = {}
    for k, label in KEYS:
        v = ask(f"{label}\n  current: {mask(cur.get(k, ''))}\n  new value: ").strip().strip('"').strip("'")
        if v:
            if any(c.isspace() for c in v):
                say("  Skipped: a key cannot contain spaces. Check what you pasted.")
                continue
            updates[k] = v
    if updates:
        write_env(env_path, lines, updates)
        say(f"\nSaved {len(updates)} key(s) to {env_path.name}: {', '.join(updates)}")
    else:
        say("\nNo changes made.")
    key = updates.get("NASA_API_KEY") or cur.get("NASA_API_KEY")
    if test_nasa and key:
        try:
            import httpx
            r = httpx.get("https://api.nasa.gov/DONKI/FLR", params={"api_key": key}, timeout=20)
            say(f"NASA key test: HTTP {r.status_code}. " + ("The key works." if r.status_code == 200 else "NASA rejected the key or is rate-limiting. Check the key at https://api.nasa.gov/."))
        except Exception as e:  # noqa: BLE001
            say(f"NASA key test could not run ({type(e).__name__}). Check your internet connection.")
    say("\nRestart CipherPulse (close its window and run start.bat) so the new keys are used.")
    return updates


if __name__ == "__main__":
    run(ROOT / ".env")
