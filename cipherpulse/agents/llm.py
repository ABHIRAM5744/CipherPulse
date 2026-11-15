"""Provider chain: Claude -> Groq -> Gemini -> (caller falls back to templates).

Keys come only from environment / .env. A provider that errors is parked for 2 minutes
so a bad key never slows the live pipeline.
"""
import json
import re
import time

import httpx

from .. import config

_parked = {}


def available():
    out = []
    if config.get("ANTHROPIC_API_KEY"):
        out.append("claude")
    if config.get("GROQ_API_KEY"):
        out.append("groq")
    if config.get("GEMINI_API_KEY"):
        out.append("gemini")
    return out


async def _claude(system, user):
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": config.get("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
            json={"model": config.get("CLAUDE_MODEL", "claude-sonnet-5-5"), "max_tokens": 400,
                  "system": system, "messages": [{"role": "user", "content": user}]},
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])


async def _groq(system, user):
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {config.get('GROQ_API_KEY')}"},
            json={"model": config.get("GROQ_MODEL", "llama-3.3-70b-versatile"), "max_tokens": 400,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def _gemini(system, user):
    model = config.get("GEMINI_MODEL", "gemini-2.0-flash")
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": config.get("GEMINI_API_KEY")},
            json={"systemInstruction": {"parts": [{"text": system}]},
                  "contents": [{"role": "user", "parts": [{"text": user}]}]},
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


PROVIDERS = {"claude": _claude, "groq": _groq, "gemini": _gemini}


async def complete(system: str, user: str):
    """Returns (text, provider). Raises RuntimeError if no provider works."""
    for name in available():
        if _parked.get(name, 0) > time.time():
            continue
        try:
            return await PROVIDERS[name](system, user), name
        except Exception as e:
            _parked[name] = time.time() + 120
            print(f"[llm] {name} failed ({type(e).__name__}); parked 120s", flush=True)
    raise RuntimeError("no LLM provider available")


def parse_json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)
