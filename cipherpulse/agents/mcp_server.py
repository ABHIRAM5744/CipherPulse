"""MCP server: lets any MCP client (Claude Desktop, Claude Code, agents) query the live system.

Run:  python -m cipherpulse.agents.mcp_server     (gateway must be running)
"""
import httpx
try:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:  # mcp 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as FastMCP

from .. import config

BASE = f"http://{config.HOST}:{config.PORT}"
mcp = FastMCP("cipherpulse")


def _get(path):
    return httpx.get(BASE + path, timeout=10).json()


@mcp.tool()
def get_crew_status() -> dict:
    """Live vitals, status and counters for every astronaut."""
    return _get("/api/state")


@mcp.tool()
def get_recent_alerts(limit: int = 10) -> list:
    """Most recent health/security alerts with AI explanations."""
    return _get("/api/alerts")[:limit]


@mcp.tool()
def verify_integrity() -> dict:
    """Re-walk the encrypted hash chain and report whether any record was altered."""
    return httpx.post(BASE + "/api/integrity/verify", timeout=30).json()


@mcp.tool()
def get_history(astronaut: str, limit: int = 30) -> list:
    """Decrypted recent vitals history for one astronaut (e.g. A2)."""
    return _get(f"/api/history/{astronaut}")[-limit:]


if __name__ == "__main__":
    mcp.run()
