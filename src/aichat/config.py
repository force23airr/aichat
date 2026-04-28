from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class AgentSpec:
    """Named participant with a role and provider/model binding."""

    name: str
    model: str
    role: str = ""
    provider: str | None = None
    mcp_servers: list[str] = field(default_factory=list)

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

    raw_agents = raw.get("agents") or []
    if not isinstance(raw_agents, list) or not raw_agents:
        raise ValueError("Config file must define a non-empty 'agents' list")

    agents = [_parse_agent(item) for item in raw_agents]
    names = [agent.name for agent in agents]
    duplicate_names = sorted({name for name in names if names.count(name) > 1})
    if duplicate_names:
        raise ValueError(f"Duplicate agent names in config: {', '.join(duplicate_names)}")

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
        agents=agents,
    )


def _parse_agent(item: Any) -> AgentSpec:
    if not isinstance(item, dict):
        raise ValueError("Each agent must be a YAML mapping")
    name = _required_str(item, "name")
    model = _required_str(item, "model")
    provider = item.get("provider")
    role = item.get("role") or ""
    if provider is not None and not isinstance(provider, str):
        raise ValueError(f"Agent '{name}' provider must be a string")
    if not isinstance(role, str):
        raise ValueError(f"Agent '{name}' role must be a string")
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
    )


def _required_str(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Agent is missing required string field '{key}'")
    return value.strip()
