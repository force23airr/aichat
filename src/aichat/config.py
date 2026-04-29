from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class MCPServerSpec:
    """Configured MCP server declaration.

    This is a contract only for now. The runtime validates and exposes these
    declarations to agents, but actual MCP process execution is a later layer.
    """

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class AgentSpec:
    """Named participant with a role and provider/model binding."""

    name: str
    model: str
    role: str = ""
    provider: str | None = None
    mcp_servers: list[str] = field(default_factory=list)
    command: str | None = None
    command_args: list[str] = field(default_factory=list)
    command_env: dict[str, str] = field(default_factory=dict)
    command_timeout: int = 120

    @property
    def provider_alias(self) -> str:
        if self.provider:
            return self.provider
        if ":" in self.model:
            return self.model.split(":", 1)[0]
        return self.model

    @property
    def model_name(self) -> str | None:
        if ":" in self.model:
            return self.model.split(":", 1)[1]
        return None

    @property
    def label(self) -> str:
        return f"{self.name}/{self.provider_alias}" if self.name != self.provider_alias else self.name


@dataclass(frozen=True)
class SessionConfig:
    task: str | None = None
    starter: str | None = None
    max_turns: int | None = None
    mcp_servers: dict[str, MCPServerSpec] = field(default_factory=dict)
    agents: list[AgentSpec] = field(default_factory=list)

    @property
    def participants(self) -> list[str]:
        return [agent.name for agent in self.agents]


def agents_from_participants(participants: list[str]) -> list[AgentSpec]:
    return [AgentSpec(name=participant, model=participant) for participant in participants]


def load_session_config(path: str | Path) -> SessionConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Config file must contain a YAML mapping")

    mcp_servers = _parse_mcp_servers(raw.get("mcp_servers") or {})
    raw_agents = raw.get("agents") or []
    if not isinstance(raw_agents, list) or not raw_agents:
        raise ValueError("Config file must define a non-empty 'agents' list")

    agents = [_parse_agent(item) for item in raw_agents]
    names = [agent.name for agent in agents]
    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    if duplicate_names:
        raise ValueError(f"Duplicate agent names in config: {', '.join(duplicate_names)}")
    _validate_agent_mcp_refs(agents, mcp_servers)

    starter = raw.get("starter")
    if starter is not None and starter not in names:
        raise ValueError(f"Starter '{starter}' is not defined in agents")

    max_turns = raw.get("max_turns")
    if max_turns is not None and (not isinstance(max_turns, int) or max_turns < 0):
        raise ValueError("max_turns must be a non-negative integer")

    return SessionConfig(
        task=raw.get("task"),
        starter=starter,
        max_turns=max_turns,
        mcp_servers=mcp_servers,
        agents=agents,
    )


def _parse_mcp_servers(raw: Any) -> dict[str, MCPServerSpec]:
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise ValueError("mcp_servers must be a YAML mapping")
    servers = {}
    for name, item in raw.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("mcp_servers keys must be non-empty strings")
        if not isinstance(item, dict):
            raise ValueError(f"MCP server '{name}' must be a YAML mapping")
        server = _parse_mcp_server(name.strip(), item)
        servers[server.name] = server
    return servers


def _parse_mcp_server(name: str, item: dict[str, Any]) -> MCPServerSpec:
    command = _required_str(item, "command", label=f"MCP server '{name}'")
    raw_args = item.get("args") or []
    raw_env = item.get("env") or {}
    raw_allowed_tools = item.get("allowed_tools") or []
    description = item.get("description") or ""

    if not isinstance(raw_args, list) or not all(isinstance(arg, str) for arg in raw_args):
        raise ValueError(f"MCP server '{name}' args must be a list of strings")
    if not isinstance(raw_env, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw_env.items()
    ):
        raise ValueError(f"MCP server '{name}' env must be a mapping of strings")
    if not isinstance(raw_allowed_tools, list) or not all(
        isinstance(tool, str) for tool in raw_allowed_tools
    ):
        raise ValueError(f"MCP server '{name}' allowed_tools must be a list of strings")
    if not isinstance(description, str):
        raise ValueError(f"MCP server '{name}' description must be a string")

    return MCPServerSpec(
        name=name,
        command=command,
        args=raw_args,
        env=raw_env,
        allowed_tools=raw_allowed_tools,
        description=description.strip(),
    )


def _validate_agent_mcp_refs(
    agents: list[AgentSpec],
    mcp_servers: dict[str, MCPServerSpec],
) -> None:
    known = set(mcp_servers)
    for agent in agents:
        unknown = sorted(set(agent.mcp_servers) - known)
        if unknown:
            raise ValueError(
                f"Agent '{agent.name}' references undefined MCP server(s): {', '.join(unknown)}"
            )


def _parse_agent(item: Any) -> AgentSpec:
    if not isinstance(item, dict):
        raise ValueError("Each agent must be a YAML mapping")
    name = _required_str(item, "name")
    model = _required_str(item, "model")
    provider = item.get("provider")
    role = item.get("role") or ""
    command = item.get("command")
    raw_command_args = item.get("args") or item.get("command_args") or []
    raw_command_env = item.get("env") or item.get("command_env") or {}
    command_timeout = item.get("timeout") or item.get("command_timeout") or 120
    if provider is not None and not isinstance(provider, str):
        raise ValueError(f"Agent '{name}' provider must be a string")
    if not isinstance(role, str):
        raise ValueError(f"Agent '{name}' role must be a string")
    if command is not None and not isinstance(command, str):
        raise ValueError(f"Agent '{name}' command must be a string")
    if not isinstance(raw_command_args, list) or not all(
        isinstance(arg, str) for arg in raw_command_args
    ):
        raise ValueError(f"Agent '{name}' args must be a list of strings")
    if not isinstance(raw_command_env, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw_command_env.items()
    ):
        raise ValueError(f"Agent '{name}' env must be a mapping of strings")
    if not isinstance(command_timeout, int) or command_timeout <= 0:
        raise ValueError(f"Agent '{name}' timeout must be a positive integer")
    raw_mcp_servers = item.get("mcp_servers") or []
    if not isinstance(raw_mcp_servers, list) or not all(
        isinstance(server, str) for server in raw_mcp_servers
    ):
        raise ValueError(f"Agent '{name}' mcp_servers must be a list of strings")
    return AgentSpec(
        name=name,
        model=model,
        provider=provider,
        role=role.strip(),
        mcp_servers=raw_mcp_servers,
        command=command.strip() if command else None,
        command_args=raw_command_args,
        command_env=raw_command_env,
        command_timeout=command_timeout,
    )


def _required_str(item: dict[str, Any], key: str, label: str = "Agent") -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} is missing required string field '{key}'")
    return value.strip()
