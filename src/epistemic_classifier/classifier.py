from __future__ import annotations

import asyncio
import json
import os
import random
import time
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from .cache import ClassificationCache, json_dumps
from .prompts import PROMPT_VERSION, build_prompt
from .schema import (
    Classification,
    EpistemicType,
    FactualSubtype,
    TranscriptClassification,
    Verifiability,
)
from .segmenter import parse_transcript, strip_markdown


# HTTP status codes that indicate a transient error worth retrying.
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}


def _retry_after_seconds(exc: httpx.HTTPStatusError) -> float | None:
    """Parse a Retry-After header (seconds form) from a 429/5xx response."""
    retry_after = exc.response.headers.get("retry-after")
    if not retry_after:
        return None
    try:
        return float(retry_after)
    except ValueError:
        return None  # HTTP-date form is unsupported in v1


DEFAULT_MODEL = "claude-haiku-4-5-20251001"
LOG_PATH_ENV = "EPISTEMIC_CLASSIFIER_LOG_PATH"
DEFAULT_STATE_DIR = Path.home() / ".epistemic_classifier"


class MalformedClassification(ValueError):
    pass


class ClassificationProvider(Protocol):
    async def classify(self, prompt: str, model: str) -> dict[str, Any]:
        ...


def _model_validate(data: dict[str, Any], sentence: str) -> Classification:
    data = dict(data)
    data["sentence"] = sentence
    if data.get("epistemic_type") != EpistemicType.FACTUAL_ASSERTION.value:
        data["subtype"] = None
    try:
        if hasattr(Classification, "model_validate"):
            return Classification.model_validate(data)
        return Classification.parse_obj(data)
    except ValidationError as exc:
        raise MalformedClassification(str(exc)) from exc


def _json_from_text(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise MalformedClassification("No JSON object found in provider response")
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise MalformedClassification(str(exc)) from exc


def fallback_classification(sentence: str, error: Exception | None = None) -> Classification:
    reason = "Classification failed, defaulting to factual_assertion for safety"
    if error is not None:
        # Surface the underlying error so failures aren't silent. Reasoning
        # is the only free-text field on Classification, so it's where the
        # diagnostic has to live to flow through to the JSONL log.
        reason = f"{reason} ({type(error).__name__}: {str(error)[:200]})"
    return Classification(
        sentence=sentence,
        epistemic_type=EpistemicType.FACTUAL_ASSERTION,
        verifiability=Verifiability.VERIFIABLE,
        subtype=FactualSubtype.EXISTENTIAL,
        hedge_markers=[],
        confidence=0.0,
        reasoning=reason,
    )


class _SharedClientMixin:
    """Lazily creates and reuses one httpx.AsyncClient per provider instance.
    Reusing the client (and its connection pool) avoids spawning a fresh DNS
    lookup + TCP handshake for every classification, which can exhaust the
    macOS DNS resolver under load and cause sporadic ConnectError failures.
    """

    _client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()


class AnthropicProvider(_SharedClientMixin):
    def __init__(self, api_key: str | None = None, endpoint: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.endpoint = endpoint or "https://api.anthropic.com/v1/messages"

    async def classify(self, prompt: str, model: str) -> dict[str, Any]:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 500,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [
                {
                    "name": "classify_sentence",
                    "description": "Return the epistemic classification for one sentence.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "epistemic_type": {
                                "type": "string",
                                "enum": [
                                    "factual_assertion",
                                    "opinion",
                                    "prediction",
                                    "recommendation",
                                    "hypothetical",
                                    "question",
                                    "meta",
                                ],
                            },
                            "verifiability": {
                                "type": "string",
                                "enum": [
                                    "verifiable",
                                    "unverifiable_in_principle",
                                    "verifiable_only_post_hoc",
                                ],
                            },
                            "subtype": {
                                "type": ["string", "null"],
                                "enum": [
                                    "numeric_temporal",
                                    "entity_relation",
                                    "categorical",
                                    "causal",
                                    "comparative",
                                    "existential",
                                    "definitional",
                                    None,
                                ],
                            },
                            "hedge_markers": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "reasoning": {"type": "string"},
                        },
                        "required": [
                            "epistemic_type",
                            "verifiability",
                            "subtype",
                            "hedge_markers",
                            "confidence",
                            "reasoning",
                        ],
                        "additionalProperties": False,
                    },
                }
            ],
            "tool_choice": {"type": "tool", "name": "classify_sentence"},
        }
        client = self._get_client()
        response = await client.post(self.endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        for block in data.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "classify_sentence":
                return block["input"]
        return _json_from_text(data["content"][0]["text"])


class OpenAICompatibleProvider(_SharedClientMixin):
    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        auth_header: str | None = None,
    ):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.endpoint = endpoint or os.environ.get(
            "EPISTEMIC_CLASSIFIER_OPENAI_ENDPOINT",
            "https://api.openai.com/v1/chat/completions",
        )
        self.auth_header = auth_header or "Authorization: Bearer {api_key}"

    async def classify(self, prompt: str, model: str) -> dict[str, Any]:
        if model.startswith("openai:"):
            model = model.split(":", 1)[1]
        headers = {"content-type": "application/json"}
        if self.api_key and self.auth_header:
            key, value = self.auth_header.format(api_key=self.api_key).split(": ", 1)
            headers[key] = value
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 500,
            "response_format": {"type": "json_object"},
        }
        client = self._get_client()
        response = await client.post(self.endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return _json_from_text(data["choices"][0]["message"]["content"])


class OllamaProvider(OpenAICompatibleProvider):
    def __init__(self, endpoint: str | None = None):
        super().__init__(
            api_key="",
            endpoint=endpoint or os.environ.get(
                "EPISTEMIC_CLASSIFIER_OLLAMA_ENDPOINT",
                "http://localhost:11434/v1/chat/completions",
            ),
            auth_header="",
        )

    async def classify(self, prompt: str, model: str) -> dict[str, Any]:
        if model.startswith("ollama:"):
            model = model.split(":", 1)[1]
        return await super().classify(prompt, model)


def provider_for_model(model: str) -> ClassificationProvider:
    if model.startswith("ollama:"):
        return OllamaProvider()
    if model.startswith("openai:") or model.startswith("gpt-"):
        return OpenAICompatibleProvider()
    return AnthropicProvider()


class EpistemicClassifier:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        provider: ClassificationProvider | None = None,
        cache: ClassificationCache | None = None,
        log_path: str | Path | None = None,
    ):
        self.model = model
        self.provider = provider or provider_for_model(model)
        self.cache = cache or ClassificationCache()
        self.log_path = Path(
            log_path or os.environ.get(LOG_PATH_ENV, DEFAULT_STATE_DIR / "classifications.jsonl")
        ).expanduser()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    async def classify_sentence(
        self,
        sentence: str,
        prior_sentence: str | None = None,
        speaker: str | None = None,
    ) -> Classification:
        started = time.perf_counter()
        prompt_sentence = strip_markdown(sentence)
        prompt_prior = strip_markdown(prior_sentence) if prior_sentence else None

        cached = self.cache.get(
            self.model, prompt_sentence, prompt_prior, prompt_version=PROMPT_VERSION
        )
        if cached:
            result = Classification(
                sentence=sentence,
                epistemic_type=cached.epistemic_type,
                verifiability=cached.verifiability,
                subtype=cached.subtype,
                hedge_markers=cached.hedge_markers,
                confidence=cached.confidence,
                reasoning=cached.reasoning,
            )
            self._log(sentence, result, started, cache_hit=True, speaker=speaker)
            return result

        result = await self._classify_uncached(sentence, prompt_sentence, prompt_prior)
        if result.confidence > 0.0:
            self.cache.set(
                self.model, prompt_sentence, prompt_prior, result, prompt_version=PROMPT_VERSION
            )
        self._log(sentence, result, started, cache_hit=False, speaker=speaker)
        return result

    async def classify_many(
        self,
        sentences: list[tuple[str, str | None, str | None]],
        concurrency: int = 4,
    ) -> list[Classification]:
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(item: tuple[str, str | None, str | None]) -> Classification:
            sentence, prior_sentence, speaker = item
            async with semaphore:
                return await self.classify_sentence(sentence, prior_sentence, speaker)

        return await asyncio.gather(*(run_one(item) for item in sentences))

    async def classify_transcript(
        self,
        transcript_path: str | Path,
        concurrency: int = 4,
    ) -> list[TranscriptClassification]:
        segments = parse_transcript(transcript_path)
        inputs = [(segment.original, segment.prior_sentence, segment.speaker) for segment in segments]
        try:
            classifications = await self.classify_many(inputs, concurrency=concurrency)
        finally:
            # Close the provider's pooled client so we don't leak connections.
            aclose = getattr(self.provider, "aclose", None)
            if aclose is not None:
                await aclose()
        return [
            TranscriptClassification(
                speaker=segment.speaker,
                sentence_index=segment.sentence_index,
                classification=classification,
            )
            for segment, classification in zip(segments, classifications)
        ]

    async def _classify_uncached(
        self,
        original_sentence: str,
        prompt_sentence: str,
        prompt_prior: str | None,
    ) -> Classification:
        prompt = build_prompt(prompt_sentence, prompt_prior)
        last_exc: Exception | None = None
        # 5 attempts (was 3) so transient 429 storms can clear; max backoff
        # ~60s lets us ride out a full per-minute rate-limit window without
        # giving up.
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                raw = await self.provider.classify(prompt, self.model)
                return _model_validate(raw, original_sentence)
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                # 4xx other than 429 are not transient — fall through to fallback.
                if exc.response.status_code not in _RETRYABLE_STATUS:
                    break
                if attempt == max_attempts - 1:
                    break
                # Honor Retry-After when present; otherwise exponential backoff
                # with jitter so concurrent retries don't all hit the API at the
                # same instant (thundering herd).
                delay = _retry_after_seconds(exc)
                if delay is None:
                    delay = min(2 ** (attempt + 1), 60) + random.uniform(0, 2.0)
                await asyncio.sleep(delay)
            except httpx.TransportError as exc:
                # ConnectError, ReadTimeout, etc. — transient network/DNS,
                # use long backoff with jitter (same as 429 path).
                last_exc = exc
                if attempt == max_attempts - 1:
                    break
                await asyncio.sleep(min(2 ** (attempt + 1), 60) + random.uniform(0, 2.0))
            except (
                httpx.HTTPError,
                MalformedClassification,
                ValidationError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                # Validation/parse errors are deterministic at temperature=0,
                # so retrying rarely helps — keep these short.
                last_exc = exc
                if attempt == max_attempts - 1:
                    break
                await asyncio.sleep(min(2**attempt, 4))
        return fallback_classification(original_sentence, error=last_exc)

    def _log(
        self,
        sentence: str,
        classification: Classification,
        started: float,
        cache_hit: bool,
        speaker: str | None = None,
    ) -> None:
        if hasattr(classification, "model_dump"):
            output = classification.model_dump(mode="json")
        else:
            output = json.loads(classification.json())
        record = {
            "sentence": sentence,
            "speaker": speaker,
            "model": self.model,
            "output": output,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "cache_hit": cache_hit,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json_dumps(record) + "\n")


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("Use EpistemicClassifier async methods from an existing event loop")


def classify_sentence(
    sentence: str,
    prior_sentence: str | None = None,
    speaker: str | None = None,
    model: str = DEFAULT_MODEL,
) -> Classification:
    classifier = EpistemicClassifier(model=model)
    return _run(classifier.classify_sentence(sentence, prior_sentence, speaker))


def classify_transcript(
    transcript_path: str | Path,
    model: str = DEFAULT_MODEL,
    concurrency: int = 4,
) -> list[TranscriptClassification]:
    classifier = EpistemicClassifier(model=model)
    return _run(classifier.classify_transcript(transcript_path, concurrency=concurrency))
