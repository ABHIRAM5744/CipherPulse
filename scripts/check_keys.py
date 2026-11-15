"""Tests each configured key with one tiny request and says plainly whether it works. Run on your PC: check_keys.bat"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx  # noqa: E402

from cipherpulse import config  # noqa: E402,F401  (loads .env and keys.env)


def snip(r):
    try:
        j = r.json()
        e = j.get("error", j)
        return (e.get("message") if isinstance(e, dict) else str(e))[:160]
    except Exception:  # noqa: BLE001
        return r.text[:160]


def verdict(name, r):
    if r.status_code == 200:
        return True, "works"
    hint = {401: "key rejected: wrong, expired, or not a key for this service", 403: "key rejected or not allowed for this API",
            404: "model name not found: set the *_MODEL value in .env to a model your account can use", 429: "rate limit or quota reached: the key itself may be fine"}.get(r.status_code, "unexpected response")
    return False, f"HTTP {r.status_code}: {hint}. Service said: {snip(r)}"


def run_checks(client=None, say=print):
    c = client or httpx.Client(timeout=25)
    env = os.environ.get
    results = {}

    def test(name, var, fn):
        key = env(var, "").strip()
        if not key:
            results[name] = (None, f"{var} is not set")
        else:
            try:
                results[name] = verdict(name, fn(key))
            except Exception as e:  # noqa: BLE001
                results[name] = (False, f"could not connect ({type(e).__name__}). Check your internet connection")
        ok, msg = results[name]
        say(f"  {'PASS' if ok else ('SKIP' if ok is None else 'FAIL'):4}  {name}: {msg}")

    test("NASA", "NASA_API_KEY", lambda k: c.get("https://api.nasa.gov/DONKI/FLR", params={"api_key": k}))
    test("Claude (Anthropic)", "ANTHROPIC_API_KEY", lambda k: c.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": k, "anthropic-version": "2023-06-01"},
         json={"model": env("CLAUDE_MODEL", "claude-sonnet-5-5"), "max_tokens": 8, "messages": [{"role": "user", "content": "Say OK"}]}))
    test("Groq", "GROQ_API_KEY", lambda k: c.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {k}"},
         json={"model": env("GROQ_MODEL", "llama-3.3-70b-versatile"), "max_tokens": 8, "messages": [{"role": "user", "content": "Say OK"}]}))
    test("Gemini", "GEMINI_API_KEY", lambda k: c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{env('GEMINI_MODEL', 'gemini-2.0-flash')}:generateContent",
         headers={"x-goog-api-key": k}, json={"contents": [{"role": "user", "parts": [{"text": "Say OK"}]}]}))
    if env("VOICE_API_KEY"):
        say("  SKIP  Voice: key is set, but its provider is not known, so the app does not use it yet")
    else:
        say("  SKIP  Voice: VOICE_API_KEY is not set")
    return results


if __name__ == "__main__":
    print("\nChecking your keys (one tiny request each)...\n")
    res = run_checks()
    print("\nA FAIL means that service will fall back to built-in rules. The app keeps working.")
    sys.exit(0)
