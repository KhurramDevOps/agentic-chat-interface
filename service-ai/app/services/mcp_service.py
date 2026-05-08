"""
app/services/mcp_service.py
────────────────────────────
Universal MCP Manager — reads mcp_config.json and manages MCPServerStdio
subprocess lifecycles for the Agents SDK.

Architecture decision:
  We use the openai-agents SDK's native MCPServerStdio class rather than
  the raw `mcp` Python package. The SDK handles tool listing, schema
  translation, tool call routing, and result injection into the model
  context automatically when MCPServer instances are passed to Agent().

  This means:
    - No custom tool-call loop needed in swarm.py
    - No manual OpenAI schema translation needed
    - The SDK's Runner handles everything end-to-end

Config format (mcp_config.json — Claude Desktop compatible):
  {
    "mcpServers": {
      "<server_name>": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"},
        "agent": "ResearchAgent"   ← optional: which agent gets this server
      }
    }
  }

  Environment variable placeholders (${VAR}) in env values are resolved
  from the process environment at startup.

Constitution compliance:
  - No MongoDB imports or connections.
  - Subprocess lifecycle is managed cleanly via connect()/cleanup().
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from agents.mcp import MCPServerStdio, MCPServerStdioParams

from app.core.logging import get_logger

logger = get_logger(__name__)

# Resolve config path relative to repo root (two levels up from this file)
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "mcp_config.json"

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_vars(value: str) -> str:
    """Replace ${VAR} placeholders with values from the process environment."""
    def _replace(match: re.Match) -> str:
        var = match.group(1)
        resolved = os.environ.get(var, "")
        if not resolved:
            logger.warning("MCP config: env var '%s' is not set.", var)
        return resolved
    return _ENV_VAR_RE.sub(_replace, value)


class MCPManager:
    """
    Manages the lifecycle of all MCP server subprocesses defined in
    mcp_config.json.

    Usage (via lifespan):
        manager = get_mcp_manager()
        await manager.start()          # connect all configured servers
        ...
        await manager.shutdown()       # clean up all subprocesses

    Agent integration:
        servers = manager.servers_for_agent("ResearchAgent")
        agent = Agent(name="ResearchAgent", mcp_servers=servers, ...)
    """

    def __init__(self, config_path: Path = _DEFAULT_CONFIG_PATH) -> None:
        self._config_path = config_path
        # server_name → MCPServerStdio instance
        self._servers: dict[str, MCPServerStdio] = {}
        # server_name → agent name it belongs to (optional)
        self._server_agents: dict[str, str] = {}
        self._started = False

    async def start(self) -> None:
        """
        Load mcp_config.json, spawn all configured MCP server subprocesses,
        and connect sessions. Safe to call multiple times (idempotent).
        """
        if self._started:
            return

        if not self._config_path.exists():
            logger.warning(
                "mcp_config.json not found at %s — no MCP servers will be loaded.",
                self._config_path,
            )
            self._started = True
            return

        try:
            raw = self._config_path.read_text(encoding="utf-8")
            config: dict[str, Any] = json.loads(raw)
        except Exception as exc:
            logger.error("Failed to parse mcp_config.json: %s", exc)
            self._started = True
            return

        mcp_servers: dict[str, Any] = config.get("mcpServers", {})
        if not mcp_servers:
            logger.info("mcp_config.json has no mcpServers defined.")
            self._started = True
            return

        for server_name, server_cfg in mcp_servers.items():
            await self._start_server(server_name, server_cfg)

        self._started = True
        logger.info(
            "MCPManager started — %d server(s) active: %s",
            len(self._servers),
            list(self._servers.keys()),
        )

    async def _start_server(self, name: str, cfg: dict[str, Any]) -> None:
        """Spawn a single MCP server subprocess and connect its session."""
        command: str = cfg.get("command", "")
        args: list[str] = cfg.get("args", [])
        raw_env: dict[str, str] = cfg.get("env", {})
        agent_name: str = cfg.get("agent", "")

        if not command:
            logger.warning("MCP server '%s' has no command — skipping.", name)
            return

        # Resolve ${VAR} placeholders in env values
        resolved_env = {k: _resolve_env_vars(v) for k, v in raw_env.items()}

        # Merge with current process env so the subprocess inherits PATH etc.
        full_env = {**os.environ, **resolved_env}

        params = MCPServerStdioParams(
            command=command,
            args=args,
            env=full_env,
        )

        server = MCPServerStdio(
            params=params,
            name=name,
            cache_tools_list=True,   # cache tool list after first list_tools call
        )

        try:
            await server.connect()
            self._servers[name] = server
            if agent_name:
                self._server_agents[name] = agent_name
            logger.info("MCP server '%s' connected (agent=%s).", name, agent_name or "any")
        except Exception as exc:
            logger.warning(
                "MCP server '%s' failed to connect: %s — continuing without it.",
                name, exc,
            )

    async def shutdown(self) -> None:
        """Clean up all MCP server subprocesses."""
        for name, server in list(self._servers.items()):
            try:
                await server.cleanup()
                logger.info("MCP server '%s' shut down.", name)
            except Exception as exc:
                logger.warning("Error shutting down MCP server '%s': %s", name, exc)
        self._servers.clear()
        self._server_agents.clear()
        self._started = False

    def servers_for_agent(self, agent_name: str) -> list[MCPServerStdio]:
        """
        Return all MCP servers assigned to a specific agent.
        Servers with no agent assignment are returned for every agent.
        """
        result = []
        for server_name, server in self._servers.items():
            assigned = self._server_agents.get(server_name, "")
            if not assigned or assigned == agent_name:
                result.append(server)
        return result

    @property
    def active_server_names(self) -> list[str]:
        return list(self._servers.keys())

    @property
    def is_started(self) -> bool:
        return self._started


# ── Singleton ─────────────────────────────────────────────────────────────────

_mcp_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    """Return the process-wide MCPManager singleton."""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
        logger.info("MCPManager instance created.")
    return _mcp_manager
