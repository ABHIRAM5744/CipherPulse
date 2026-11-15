"""Flight-surgeon agent as a LangGraph state machine:

   recall -> analyze (LLM) -> guard (safety rules) -> memorize

Falls back to a sequential runner if langgraph is not installed, and to
rule-based text if no LLM key works. Prototype advice only, not a medical device.
"""
from typing import TypedDict

from . import llm
from .memory import CrewMemory

memory = CrewMemory()

SYSTEM = (
    "You are the on-board flight-surgeon assistant in a SIMULATED astronaut health monitor "
    "(hackathon prototype, not a medical device). Given live vitals, the detector's finding and "
    "recent history, reply with JSON only: "
    '{"explanation": "<=45 words, plain language", "actions": ["<=3 short, safe operational steps"], "confidence": 0-1}. '
    "Never give drug doses. Prefer checking environment (CO2, temperature, radiation shielding), rest, and contacting ground."
)

TEMPLATES = {
    "air_quality": ("Heart rate and breathing are up while oxygen is dropping together. That pattern points to rising cabin CO2 or low oxygen, not just exertion.",
                    ["Check CO2 scrubber and cabin O2 levels", "Have the crew member stop strenuous activity", "Alert ground medical"]),
    "exertion": ("Heart and breathing rates are elevated with normal oxygen, consistent with exercise or exertion.",
                 ["Confirm the crew member is exercising", "Re-check after 5 minutes of rest"]),
    "fever_pattern": ("Body temperature and heart rate are both rising, which can indicate infection or heat stress.",
                      ["Check cabin temperature", "Hydrate and rest", "Alert ground medical"]),
    "radiation_event": ("Radiation dose rate has jumped above the safe limit, possibly a solar particle event.",
                        ["Move crew to the shielded storm shelter", "Log cumulative dose", "Alert ground"]),
    "low_oxygen": ("Blood oxygen is below the safe range while other vitals are steady.",
                   ["Check sensor fit", "Check cabin O2", "Alert ground if it persists"]),
}
DEFAULT_T = ("One or more vitals left the safe range.", ["Re-check the sensor", "Monitor closely", "Alert ground if it persists"])


class S(TypedDict, total=False):
    astro: str
    vitals: dict
    finding: dict
    memories: list
    analysis: dict
    provider: str


async def n_recall(s: S) -> S:
    return {"memories": memory.recall(s["astro"])}


async def n_analyze(s: S) -> S:
    f = s["finding"]
    user = (f"Astronaut {s['astro']}. Vitals: {s['vitals']}. Detector: severity={f['severity']}, kind={f['kind']}, "
            f"reasons={f['reasons']}, mission phase={f.get('phase','orbit')}, seconds_to_limit={f.get('eta_s')}. Earlier events: {s.get('memories') or 'none'}.")
    try:
        text, provider = await llm.complete(SYSTEM, user)
        a = llm.parse_json(text)
        a["actions"] = [str(x) for x in a.get("actions", [])][:3]
        return {"analysis": a, "provider": provider}
    except Exception:
        if f["kind"].startswith("trend_"):
            exp = (f["reasons"][0] if f.get("reasons") else "A vital sign is trending toward its limit.") + \
                  " This is an early warning: nothing has crossed a limit yet."
            acts = ["Check the cabin environment now", "Re-check in 30 seconds", "Prepare to alert ground if the trend continues"]
        else:
            exp, acts = TEMPLATES.get(f["kind"], DEFAULT_T)
        return {"analysis": {"explanation": exp, "actions": acts, "confidence": 0.6}, "provider": "rules"}


async def n_guard(s: S) -> S:
    a = dict(s["analysis"])
    a["explanation"] = str(a.get("explanation", ""))[:400]
    if s["finding"]["severity"] == "critical":
        a["actions"] = (a.get("actions", []) + ["Escalate to ground flight surgeon now"])[:4]
    a["disclaimer"] = "Simulated prototype, not medical advice."
    return {"analysis": a}


async def n_memorize(s: S) -> S:
    f = s["finding"]
    memory.add(s["astro"], f"{f['kind']} ({f['severity']}) hr={s['vitals']['hr']} spo2={s['vitals']['spo2']}")
    return {}


try:
    from langgraph.graph import END, START, StateGraph

    _g = StateGraph(S)
    for name, fn in [("recall", n_recall), ("analyze", n_analyze), ("guard", n_guard), ("memorize", n_memorize)]:
        _g.add_node(name, fn)
    _g.add_edge(START, "recall")
    _g.add_edge("recall", "analyze")
    _g.add_edge("analyze", "guard")
    _g.add_edge("guard", "memorize")
    _g.add_edge("memorize", END)
    _app = _g.compile()
    ENGINE = "langgraph"
except Exception:  # pragma: no cover
    _app = None
    ENGINE = "sequential"


async def explain(astro, vitals, finding: dict):
    state = {"astro": astro, "vitals": vitals, "finding": finding}
    if _app:
        out = await _app.ainvoke(state)
    else:
        for fn in (n_recall, n_analyze, n_guard, n_memorize):
            state.update(await fn(state))
        out = state
    return {**out["analysis"], "provider": out.get("provider", "rules"), "engine": ENGINE}


async def chat(question: str, context: str):
    sys = ("You are CipherPulse mission AI for a simulated astronaut health monitor. Answer in at most 60 words, "
           "plain spoken language (it will be read aloud). Use only the live context given. Not medical advice.")
    text, provider = await llm.complete(sys, f"Live context:\n{context}\n\nQuestion: {question}")
    return text.strip(), provider
