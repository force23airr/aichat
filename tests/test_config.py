from pathlib import Path

import pytest

from aichat.config import AgentSpec, MCPServerSpec, agents_from_participants, load_session_config


def test_load_session_config_with_named_agents(tmp_path):
    path = tmp_path / "aichat.yaml"
    path.write_text(
        """
task: "Plan a launch"
starter: planner
max_turns: 4
mcp_servers:
  filesystem:
    command: "mcp-server-filesystem"
    args: ["/workspace"]
    env:
      LOG_LEVEL: "info"
    description: "Read mounted workspace files."
    allowed_tools: ["list_directory", "read_file"]
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
    assert config.mcp_servers["filesystem"] == MCPServerSpec(
        name="filesystem",
        command="mcp-server-filesystem",
        args=["/workspace"],
        env={"LOG_LEVEL": "info"},
        allowed_tools=["list_directory", "read_file"],
        description="Read mounted workspace files.",
    )


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


def test_load_session_config_rejects_unknown_mcp_server_ref(tmp_path):
    path = tmp_path / "aichat.yaml"
    path.write_text(
        """
agents:
  - name: researcher
    model: claude
    mcp_servers: ["missing"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="undefined MCP server"):
        load_session_config(path)


def test_load_session_config_accepts_command_agent(tmp_path):
    path = tmp_path / "command.yaml"
    path.write_text(
        """
task: "Use local CLI"
starter: local_cli
agents:
  - name: local_cli
    model: command:echo
    provider: command
    command: python
    args: ["-c", "print('hello from cli')"]
    timeout: 10
    role: "Reply through a local command."
""",
        encoding="utf-8",
    )

    config = load_session_config(path)
    agent = config.agents[0]

    assert agent.provider_alias == "command"
    assert agent.model_name == "echo"
    assert agent.command == "python"
    assert agent.command_args == ["-c", "print('hello from cli')"]
    assert agent.command_timeout == 10


def test_load_session_config_resolves_relative_command_cwd_from_config_dir(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    path = config_dir / "command.yaml"
    path.write_text(
        """
task: "Use local CLI"
starter: local_cli
agents:
  - name: local_cli
    model: command:echo
    provider: command
    command: python
    args: ["-c", "print('hello from cli')"]
    cwd: ../project
""",
        encoding="utf-8",
    )

    config = load_session_config(path)

    assert config.agents[0].command_cwd == project_dir.resolve()


def test_load_session_config_rejects_missing_command_cwd(tmp_path):
    path = tmp_path / "command.yaml"
    path.write_text(
        """
task: "Use local CLI"
starter: local_cli
agents:
  - name: local_cli
    model: command:echo
    provider: command
    command: python
    cwd: missing
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="cwd does not exist"):
        load_session_config(path)


def test_load_session_config_rejects_command_cwd_file(tmp_path):
    file_path = tmp_path / "not-a-dir.txt"
    file_path.write_text("not a directory", encoding="utf-8")
    path = tmp_path / "command.yaml"
    path.write_text(
        """
task: "Use local CLI"
starter: local_cli
agents:
  - name: local_cli
    model: command:echo
    provider: command
    command: python
    cwd: not-a-dir.txt
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="cwd is not a directory"):
        load_session_config(path)


def test_agents_from_participants_preserves_legacy_behavior():
    agents = agents_from_participants(["claude", "gpt"])

    assert agents == [
        AgentSpec(name="claude", model="claude"),
        AgentSpec(name="gpt", model="gpt"),
    ]
