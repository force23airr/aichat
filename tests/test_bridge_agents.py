import asyncio

from aichat.bridge import Bridge
from aichat.config import AgentSpec
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
            AgentSpec(name="critic", model="openai:gpt-4o-mini", role="Challenge assumptions."),
        ],
    )

    turns = asyncio.run(_collect(bridge))

    assert turns[-1][1].endswith("<<TASK_COMPLETE>>")
    assert calls[0][0] == "claude"
    assert calls[1][0] == "openai"
    assert calls[1][1] == "gpt-4o-mini"
    assert bridge.transcript.participant_metadata["planner"] == (
        "model=claude; role=Coordinate the team."
    )
    first_system_prompt = calls[0][2][0].content
    second_system_prompt = calls[1][2][0].content
    assert "Your role: Coordinate the team." in first_system_prompt
    assert "critic (openai:gpt-4o-mini): Challenge assumptions." in second_system_prompt


async def _collect(bridge):
    return [turn async for turn in bridge.stream()]
