from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


CONFIG_DIR = Path(os.environ.get("AICHAT_CONFIG_DIR", "~/.aichat")).expanduser()
CONFIG_PATH = Path(os.environ.get("AICHAT_CONFIG", CONFIG_DIR / "config.yaml")).expanduser()
LOCAL_ENV_PATH = Path(".env")

PROVIDER_ENV_VARS = {
    "claude": "ANTHROPIC_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gpt": "OPENAI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "google": "GOOGLE_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "together": "TOGETHER_API_KEY",
    "perplexity": "PPLX_API_KEY",
}


@dataclass(frozen=True)
class ProviderStatus:
    provider: str
    configured: bool
    detail: str


def load_dotenv(path: str | Path = LOCAL_ENV_PATH) -> list[str]:
    """Load simple KEY=VALUE pairs from a .env file without overriding env."""
    env_path = Path(path)
    if not env_path.exists():
        return []

    loaded: list[str] = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded


def load_user_config(path: str | Path = CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path).expanduser()
    if not config_path.exists():
        return {}
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"User config must be a YAML mapping: {config_path}")
    return raw


def save_user_config(config: dict[str, Any], path: str | Path = CONFIG_PATH) -> Path:
    config_path = Path(path).expanduser()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=True), encoding="utf-8")
    return config_path


def configured_providers() -> dict[str, str]:
    config = load_user_config()
    providers = config.get("providers") or {}
    configured: dict[str, str] = {}
    if isinstance(providers, dict):
        for provider, values in providers.items():
            if isinstance(values, dict):
                api_key_env = values.get("api_key_env")
                if isinstance(api_key_env, str) and api_key_env:
                    configured[str(provider)] = api_key_env
    return configured


def provider_status(provider: str) -> ProviderStatus:
    if provider == "command":
        return ProviderStatus(
            provider=provider,
            configured=True,
            detail="local command provider; requires each command-backed agent to define command/args",
        )
    if provider == "ollama":
        return ProviderStatus(
            provider=provider,
            configured=True,
            detail="local provider; requires Ollama running at http://localhost:11434",
        )

    env_var = configured_providers().get(provider) or PROVIDER_ENV_VARS.get(provider)
    if not env_var:
        return ProviderStatus(provider=provider, configured=False, detail="unknown provider")
    if os.environ.get(env_var):
        return ProviderStatus(provider=provider, configured=True, detail=f"{env_var} is set")
    return ProviderStatus(provider=provider, configured=False, detail=f"missing {env_var}")


def providers_for_agents(agents) -> list[str]:
    providers = []
    for agent in agents:
        provider = agent.provider_alias
        if provider not in providers:
            providers.append(provider)
    return providers


def update_provider_config(provider: str, env_var: str) -> Path:
    config = load_user_config()
    providers = config.setdefault("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("User config field 'providers' must be a mapping")
    providers[provider] = {"api_key_env": env_var}
    return save_user_config(config)
