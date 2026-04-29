import os

from aichat.config import AgentSpec
from aichat.setup import load_dotenv, provider_status, providers_for_agents


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


def test_provider_status_handles_ollama_without_api_key():
    status = provider_status("ollama")

    assert status.configured is True
    assert "local provider" in status.detail


def test_providers_for_agents_uses_provider_aliases():
    providers = providers_for_agents(
        [
            AgentSpec(name="designer", model="ollama:gemma4:e2b", provider="ollama"),
            AgentSpec(name="critic", model="gpt"),
            AgentSpec(name="reviewer", model="openai:gpt-4o-mini"),
        ]
    )

    assert providers == ["ollama", "gpt", "openai"]
