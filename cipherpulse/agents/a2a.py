"""Minimal A2A (agent-to-agent) surface: an Agent Card and a JSON-RPC message/send endpoint."""
import uuid

CARD = {
    "name": "CipherPulse Flight Surgeon",
    "description": "Monitors signed, encrypted astronaut vitals in real time and answers health/security questions.",
    "url": "http://localhost:8000/a2a",
    "version": "1.0.0",
    "capabilities": {"streaming": False},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {"id": "crew_status", "name": "Crew status", "description": "Current vitals and status per astronaut", "tags": ["health"]},
        {"id": "integrity", "name": "Integrity check", "description": "Verify the tamper-evident hash chain", "tags": ["security"]},
    ],
}


def wrap_reply(rpc_id, text):
    return {"jsonrpc": "2.0", "id": rpc_id, "result": {
        "kind": "message", "role": "agent", "messageId": str(uuid.uuid4()),
        "parts": [{"kind": "text", "text": text}]}}


def extract_text(params: dict) -> str:
    msg = (params or {}).get("message", {})
    return " ".join(p.get("text", "") for p in msg.get("parts", []) if p.get("kind") == "text").strip()
