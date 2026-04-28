from pathlib import Path

import pytest

from aichat.config import AgentSpec, agents_from_participants, load_session_config


def test_load_session_config_with_named_agents(tmp_path):
    path = tmp_path / "aichat.yaml"
    path.write_text(
        """
task: "Plan a launch"
starter: planner
max_turns: 4
agents:
  - name: planner
    model: claude
    role: "Coordinate the team."
  - name: local_quant
    model: ollama:llama3
    provider: ollama
    role: "Explore optimization angles."
    mcp_servers: ["filesystem"]
""",
        encoding="utf-8",
    )

    config = load_session_config(path)

    assert config.task == "Plan a launch"
    assert config.starter == "planner"
    assert config.max_turns == 4
    assert config.participants == ["planner", "local_quant"]
    assert config.agents[1].provider_alias == "ollama"
    assert config.agents[1].model_name == "llama3"
    assert config.agents[1].mcp_servers == ["filesystem"]


def test_load_session_config_rejects_unknown_starter(tmp_path):
    path = tmp_path / "aichat.yaml"
    path.write_text(
        """
starter: missing
agents:
  - name: planner
    model: claude
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Starter 'missing'"):
        load_session_config(path)


def test_agents_from_participants_preserves_legacy_behavior():
    agents = agents_from_participants(["claude", "gpt"])

    assert agents == [
        AgentSpec(name="claude", model="claude"),
        AgentSpec(name="gpt", model="gpt"),
    ]
