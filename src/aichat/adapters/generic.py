"""
Generic AI model adapter – one file to rule them all.
Handles OpenAI-compatible, Anthropic, and Google Gemini APIs.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, ClassVar

import yaml
import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Message:
    role: str       # "system", "user", or "assistant"
    content: str


@dataclass
class ModelResponse:
    content: str
    model: str
    usage: Optional[Dict[str, int]] = None


# ---------------------------------------------------------------------------
# Base adapter
# ---------------------------------------------------------------------------

class BaseAdapter:
    """Common interface for all model adapters."""
    
    def __init__(self, config: Dict[str, Any], api_key: Optional[str] = None):
        self.config = config
        self.api_key = api_key

    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
        **kwargs
    ) -> ModelResponse:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Concrete adapters
# ---------------------------------------------------------------------------

class OpenAICompatibleAdapter(BaseAdapter):
    """Handles OpenAI, DeepSeek, Groq, Together, Ollama, and any compatible API."""

    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
        **kwargs
    ) -> ModelResponse:
        endpoint = self.config['endpoint']
        model = model or self.config.get('default_model')
        if not model:
            raise ValueError("No model name provided and no default_model in config")

        headers = {
            "Content-Type": "application/json"
        }
        if self.api_key and self.config.get('auth_header'):
            # The auth_header template may contain {api_key}
            header_str = self.config['auth_header'].format(api_key=self.api_key)
            key, value = header_str.split(": ", 1)
            headers[key] = value

        payload = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs
        }

        logger.debug("Calling %s with model %s", endpoint, model)
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data['choices'][0]['message']['content']
        usage = data.get('usage')
        return ModelResponse(content=content, model=model, usage=usage)


class AnthropicAdapter(BaseAdapter):
    """Handles Anthropic's Messages API."""

    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
        **kwargs
    ) -> ModelResponse:
        endpoint = self.config['endpoint']
        model = model or self.config.get('default_model')
        if not model:
            raise ValueError("No model name provided and no default_model in config")

        headers = {
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
            "anthropic-version": self.config.get('anthropic_version', '2023-06-01')
        }

        # Separate system message
        system_msg = ""
        chat_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                chat_messages.append({"role": m.role, "content": m.content})

        payload = {
            "model": model,
            "system": system_msg,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            **kwargs
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data['content'][0]['text']
        usage = data.get('usage')
        return ModelResponse(content=content, model=model, usage=usage)


class GeminiAdapter(BaseAdapter):
    """Handles Google Gemini's generateContent API."""

    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        max_tokens: int = 500,
        temperature: float = 0.7,
        **kwargs
    ) -> ModelResponse:
        model = model or self.config.get('default_model')
        if not model:
            raise ValueError("No model name provided and no default_model in config")

        # Build endpoint with model name
        endpoint = self.config['endpoint'].format(model=model)

        # Gemini uses API key as query param
        if self.config.get('api_key_param'):
            endpoint += f"?key={self.api_key}"

        headers = {"Content-Type": "application/json"}

        # Convert messages to Gemini format
        contents = []
        system_instruction = None
        for m in messages:
            if m.role == "system":
                system_instruction = m.content
            else:
                role = "user" if m.role == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": m.content}]
                })

        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature
            }
        }
        if system_instruction:
            payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content = data['candidates'][0]['content']['parts'][0]['text']
        return ModelResponse(content=content, model=model)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

# Mapping from registry 'type' to adapter class
_ADAPTER_MAP: ClassVar[Dict[str, type]] = {
    "openai-compatible": OpenAICompatibleAdapter,
    "anthropic": AnthropicAdapter,
    "gemini": GeminiAdapter,
}


def get_adapter(
    provider_alias: str,
    user_config: Optional[Dict[str, Any]] = None,
    builtin_registry_path: Optional[str] = None
) -> BaseAdapter:
    """
    Create an adapter for a given provider alias.
    
    Looks up the provider in:
    1. User config (if provided) – for endpoint/api_key overrides
    2. Built-in registry (model_registry.yaml)
    
    Falls back to 'custom' type if no match, requiring user_config to specify
    endpoint and model.
    """
    # Load built-in registry
    if builtin_registry_path is None:
        builtin_registry_path = os.path.join(os.path.dirname(__file__), 'model_registry.yaml')
    with open(builtin_registry_path, 'r') as f:
        builtin = yaml.safe_load(f).get('models', {})

    # Merge user config if any (always copy, never mutate the registry)
    config: Dict[str, Any] = {}
    if user_config and provider_alias in user_config:
        config = dict(user_config[provider_alias])
    elif provider_alias in builtin:
        config = dict(builtin[provider_alias])
    else:
        # Assume custom OpenAI-compatible
        config = dict(builtin.get('custom', {}))
        if user_config:
            config.update(user_config.get('custom', {}))

    # Substitute environment variables in endpoint and other string values
    config = _substitute_env_vars(config)

    # Determine adapter type
    adapter_type = config.get('type', 'openai-compatible')
    if adapter_type not in _ADAPTER_MAP:
        raise ValueError(f"Unsupported adapter type: {adapter_type}")

    # Retrieve API key from environment
    api_key = config.get('api_key', '')
    if api_key.startswith('${') and api_key.endswith('}'):
        env_var = api_key[2:-1]
        api_key = os.environ.get(env_var, '')
    elif api_key and not api_key.startswith('sk-') and len(api_key) < 20:
        # Might be a raw env var name without ${} – resolve as env var
        api_key = os.environ.get(api_key, api_key)

    # If api_key still empty, try from provider-specific env convention
    if not api_key:
        env_var_map = {
            'openai': 'OPENAI_API_KEY',
            'gpt': 'OPENAI_API_KEY',
            'anthropic': 'ANTHROPIC_API_KEY',
            'claude': 'ANTHROPIC_API_KEY',
            'deepseek': 'DEEPSEEK_API_KEY',
            'google': 'GOOGLE_API_KEY',
            'gemini': 'GOOGLE_API_KEY',
            'groq': 'GROQ_API_KEY',
            'together': 'TOGETHER_API_KEY',
            'perplexity': 'PPLX_API_KEY',
        }
        var_name = env_var_map.get(provider_alias)
        if var_name:
            api_key = os.environ.get(var_name, '')

    if not api_key and config.get('auth_header', '').find('{api_key}') != -1:
        # Only warn if we actually need an API key
        logger.warning("No API key found for %s; provider may reject requests.", provider_alias)

    adapter_class = _ADAPTER_MAP[adapter_type]
    return adapter_class(config, api_key=api_key)


def _substitute_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """Replace ${VAR} in string values with environment variables."""
    new_config = {}
    for key, value in config.items():
        if isinstance(value, str):
            # Simple ${VAR} substitution
            while '${' in value:
                start = value.index('${')
                end = value.index('}', start)
                var = value[start+2:end]
                env_val = os.environ.get(var, '')
                value = value[:start] + env_val + value[end+1:]
            new_config[key] = value
        else:
            new_config[key] = value
    return new_config

    