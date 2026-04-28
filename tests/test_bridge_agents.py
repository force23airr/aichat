import asyncio

from aichat.bridge import Bridge
from aichat.config import AgentSpec, MCPServerSpec
from aichat.adapters.generic import ModelResponse


class FakeAdapter:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    async def chat(self, messages, model=None, **kwargs):
        self.calls.append((self.name, model, messages))
        if len(self.calls) == 1:
            return ModelResponse(content="Opening from planner.", model=model or self.name)
        return ModelResponse(content="Review complete.\n<<TASK_COMPLETE>>", model=model or self.name)


def test_bridge_uses_agent_roles_and_provider_bindings(monkeypatch):
    calls = []

    def fake_get_adapter(provider_alias):
        return FakeAdapter(provider_alias, calls)

    monkeypatch.setattr("aichat.bridge.get_adapter", fake_get_adapter)
    bridge = Bridge(
        task="Plan a launch",
        starter="planner",
        participants=["planner", "critic"],
        max_turns=2,
        agents=[
            AgentSpec(name="planner", model="claude", role="Coordinate the team."),
            AgentSpec(
                name="critic",
                model="openai:gpt-4o-mini",
                role="Challenge assumptions.",
                mcp_servers=["filesystem"],
            ),
        ],
        mcp_servers={
            "filesystem": MCPServerSpec(
                name="filesystem",
                command="mcp-server-filesystem",
                args=["/workspace"],
                allowed_tools=["list_directory", "read_file"],
                description="Read mounted workspace files.",
            )
        },
    )

    turns = asyncio.run(_collect(bridge))

    assert turns[-1][1].endswith("<<TASK_COMPLETE>>")
    assert calls[0][0] == "claude"
    assert calls[1][0] == "openai"
    assert calls[1][1] == "gpt-4o-mini"
    assert bridge.transcript.participant_metadata["planner"] == (
        "model=claude; role=Coordinate the team."
    )
    assert bridge.transcript.participant_metadata["critic"] == (
        "model=openai:gpt-4o-mini; role=Challenge assumptions.; mcp_servers=filesystem"
    )
    first_system_prompt = calls[0][2][0].content
    second_system_prompt = calls[1][2][0].content
    assert "Your role: Coordinate the team." in first_system_prompt
    assert "Assigned MCP tools: none." in first_system_prompt
    assert "critic (openai:gpt-4o-mini): Challenge assumptions." in second_system_prompt
    assert "Assigned MCP tool surface:" in second_system_prompt
    assert "- filesystem: list_directory, read_file. Read mounted workspace files." in second_system_prompt


def test_bridge_uses_discovered_mcp_tools_in_prompt(monkeypatch):
    calls = []

    def fake_get_adapter(provider_alias):
        return FakeAdapter(provider_alias, calls)

    async def fake_discover(self):
        from aichat.mcp_runtime import DiscoveredTool

        self._mcp_tools = {
            "filesystem": [
                DiscoveredTool(server="filesystem", name="read_file", description="Read a file.")
            ]
        }

    monkeypatch.setattr("aichat.bridge.get_adapter", fake_get_adapter)
    monkeypatch.setattr(Bridge, "_discover_mcp_tools", fake_discover)
    bridge = Bridge(
        task="Inspect files",
        starter="researcher",
        participants=["researcher"],
        max_turns=0,
        agents=[
            AgentSpec(
                name="researcher",
                model="claude",
                role="Use approved tools.",
                mcp_servers=["filesystem"],
            )
        ],
        mcp_servers={
            "filesystem": MCPServerSpec(
                name="filesystem",
                command="mcp-server-filesystem",
                allowed_tools=["list_directory"],
            )
        },
        discover_mcp_tools=True,
    )

    asyncio.run(_collect(bridge))

    system_prompt = calls[0][2][0].content
    assert "- filesystem: read_file." in system_prompt


async def _collect(bridge):
    return [turn async for turn in bridge.stream()]
