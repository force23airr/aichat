import os
import sys

import httpx
import pytest

from aichat.config import AgentSpec
from aichat.setup import (
    OllamaProbe,
    command_status_for_agent,
    command_statuses_for_agents,
    discover_ollama,
    load_dotenv,
    provider_status,
    providers_for_agents,
)


def test_load_dotenv_sets_missing_values_without_overriding(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "ANTHROPIC_API_KEY=from-file\nOPENAI_API_KEY=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "existing")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    loaded = load_dotenv(env_path)

    assert loaded == ["ANTHROPIC_API_KEY"]
    assert os.environ["ANTHROPIC_API_KEY"] == "from-file"
    assert os.environ["OPENAI_API_KEY"] == "existing"


def test_provider_status_for_ollama_marks_configured_when_models_found(monkeypatch):
    monkeypatch.setattr(
        "aichat.setup.discover_ollama",
        lambda *_, **__: OllamaProbe(reachable=True, models=("gemma3:e2b",), detail="1 model(s) available"),
    )

    status = provider_status("ollama")

    assert status.configured is True


def test_provider_status_for_ollama_marks_unconfigured_when_unreachable(monkeypatch):
    monkeypatch.setattr(
        "aichat.setup.discover_ollama",
        lambda *_, **__: OllamaProbe(reachable=False, models=(), detail="Ollama daemon not reachable"),
    )

    status = provider_status("ollama")

    assert status.configured is False
    assert "not reachable" in status.detail


def test_provider_status_for_ollama_marks_unconfigured_with_no_models(monkeypatch):
    monkeypatch.setattr(
        "aichat.setup.discover_ollama",
        lambda *_, **__: OllamaProbe(reachable=True, models=(), detail="no models pulled"),
    )

    status = provider_status("ollama")

    assert status.configured is False


def test_discover_ollama_returns_models_on_success(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "gemma3:e2b"}, {"name": "llama3.1:8b"}]}

    def fake_get(url, timeout=None):
        return FakeResponse()

    monkeypatch.setattr(httpx, "get", fake_get)

    probe = discover_ollama()

    assert probe.reachable is True
    assert probe.models == ("gemma3:e2b", "llama3.1:8b")


def test_discover_ollama_handles_connection_error(monkeypatch):
    def fake_get(url, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "get", fake_get)

    probe = discover_ollama()

    assert probe.reachable is False
    assert "not reachable" in probe.detail


def test_discover_ollama_handles_running_daemon_without_models(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"models": []}

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: FakeResponse())

    probe = discover_ollama()

    assert probe.reachable is True
    assert probe.models == ()
    assert "no models" in probe.detail.lower()


def test_providers_for_agents_uses_provider_aliases():
    providers = providers_for_agents(
        [
            AgentSpec(name="designer", model="ollama:gemma4:e2b", provider="ollama"),
            AgentSpec(name="critic", model="gpt"),
            AgentSpec(name="reviewer", model="openai:gpt-4o-mini"),
        ]
    )

    assert providers == ["ollama", "gpt", "openai"]


def test_command_status_for_agent_checks_path():
    status = command_status_for_agent(
        AgentSpec(
            name="local_cli",
            model="command:python",
            provider="command",
            command=sys.executable,
        )
    )

    assert status is not None
    assert status.configured is True
    assert status.detail


def test_command_status_for_agent_reports_missing_command():
    status = command_status_for_agent(
        AgentSpec(
            name="missing_cli",
            model="command:missing",
            provider="command",
            command="aichat-definitely-missing-command",
        )
    )

    assert status is not None
    assert status.configured is False
    assert "not found on PATH" in status.detail


def test_command_statuses_ignores_regular_agents():
    statuses = command_statuses_for_agents(
        [
            AgentSpec(name="designer", model="ollama:gemma4:e2b", provider="ollama"),
            AgentSpec(name="local_cli", model="command:python", provider="command", command=sys.executable),
        ]
    )

    assert [status.agent for status in statuses] == ["local_cli"]
