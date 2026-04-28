import asyncio

from aichat.bridge import Bridge
from aichat.config import AgentSpec, MCPServerSpec
from aichat.adapters.generic import ModelResponse
from aichat.mcp_runtime import ToolResult


class FakeAdapter:
    def __init__(self, name, calls):
        self.name = name
        self.calls = calls

    async def chat(self, messages, model=None, **kwargs):
        self.calls.append((self.name, model, messages))
        if len(self.calls) == 1:
            return ModelResponse(content="Opening from planner.", model=model or self.name)
        return ModelResponse(content="Review complete.\n<<TASK_COMPLETE>>", model=model or self.name)


class SequenceAdapter:
    def __init__(self, name, calls, responses):
        self.name = name
        self.calls = calls
        self.responses = list(responses)

    async def chat(self, messages, model=None, **kwargs):
        self.calls.append((self.name, model, messages))
        return ModelResponse(content=self.responses.pop(0), model=model or self.name)


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


def test_bridge_executes_allowed_tool_call_and_continues_turn(monkeypatch):
    calls = []

    def fake_get_adapter(provider_alias):
        return SequenceAdapter(
            provider_alias,
            calls,
            [
                '<tool_call>{"server":"filesystem","tool":"read_file","arguments":{"path":"README.md"}}</tool_call>',
                "I read the README and can continue.",
            ],
        )

    async def fake_discover(self):
        from aichat.mcp_runtime import DiscoveredTool

        self._mcp_tools = {
            "filesystem": [
                DiscoveredTool(
                    server="filesystem",
                    name="read_file",
                    input_schema={
                        "type": "object",
                        "required": ["path"],
                        "properties": {"path": {"type": "string"}},
                    },
                )
            ]
        }

    async def fake_call_tool(self, tool_call):
        return ToolResult(
            server=tool_call.server,
            tool=tool_call.tool,
            arguments=tool_call.arguments,
            ok=True,
            content="# aichat\n",
        )

    monkeypatch.setattr("aichat.bridge.get_adapter", fake_get_adapter)
    monkeypatch.setattr(Bridge, "_discover_mcp_tools", fake_discover)
    monkeypatch.setattr("aichat.bridge.MCPRuntime.call_tool", fake_call_tool)
    bridge = Bridge(
        task="Read README",
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
                allowed_tools=["read_file"],
            )
        },
        enable_tool_calls=True,
    )

    turns = asyncio.run(_collect(bridge))

    assert turns == [("researcher", "I read the README and can continue.")]
    assert len(calls) == 2
    assert [entry.kind for entry in bridge.transcript.entries] == [
        "tool_call",
        "tool_result",
        "message",
    ]
    assert bridge.transcript.entries[1].content == "# aichat\n"
    assert "Tool result for filesystem.read_file" in calls[1][2][-1].content


def test_bridge_denies_unassigned_tool_call(monkeypatch):
    calls = []

    def fake_get_adapter(provider_alias):
        return SequenceAdapter(
            provider_alias,
            calls,
            [
                '<tool_call>{"server":"market_data","tool":"get_price_history","arguments":{"symbol":"AAPL"}}</tool_call>',
                "I cannot use that tool.",
            ],
        )

    async def fake_discover(self):
        self._mcp_tools = {}

    monkeypatch.setattr("aichat.bridge.get_adapter", fake_get_adapter)
    monkeypatch.setattr(Bridge, "_discover_mcp_tools", fake_discover)
    bridge = Bridge(
        task="Fetch market data",
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
            "filesystem": MCPServerSpec(name="filesystem", command="mcp-server-filesystem"),
            "market_data": MCPServerSpec(name="market_data", command="mcp-server-market-data"),
        },
        enable_tool_calls=True,
    )

    asyncio.run(_collect(bridge))

    assert bridge.transcript.entries[1].kind == "tool_result"
    assert not bridge.transcript.entries[1].metadata["ok"]
    assert "not allowed" in bridge.transcript.entries[1].content


async def _collect(bridge):
    return [turn async for turn in bridge.stream()]
