import asyncio

from epistemic_classifier.cache import ClassificationCache
from epistemic_classifier.classifier import EpistemicClassifier
from epistemic_classifier.prompts import build_prompt
from epistemic_classifier.schema import EpistemicType, Verifiability


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def classify(self, prompt, model):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_classifier_validates_provider_output_and_caches(tmp_path):
    provider = FakeProvider(
        [
            {
                "epistemic_type": "question",
                "verifiability": "unverifiable_in_principle",
                "subtype": None,
                "hedge_markers": [],
                "confidence": 0.99,
                "reasoning": "Interrogative seeking input.",
            }
        ]
    )
    classifier = EpistemicClassifier(
        model="fake-model",
        provider=provider,
        cache=ClassificationCache(tmp_path / "cache.db"),
        log_path=tmp_path / "log.jsonl",
    )

    first = asyncio.run(classifier.classify_sentence("What are your thoughts?"))
    second = asyncio.run(classifier.classify_sentence("What are your thoughts?"))

    assert first.epistemic_type == EpistemicType.QUESTION
    assert second.epistemic_type == EpistemicType.QUESTION
    assert provider.calls == 1


def test_classifier_retries_malformed_output_then_succeeds(tmp_path):
    provider = FakeProvider(
        [
            {"epistemic_type": "not-a-label"},
            {
                "epistemic_type": "opinion",
                "verifiability": "unverifiable_in_principle",
                "subtype": None,
                "hedge_markers": [],
                "confidence": 0.88,
                "reasoning": "Subjective evaluation.",
            },
        ]
    )
    classifier = EpistemicClassifier(
        model="fake-model",
        provider=provider,
        cache=ClassificationCache(tmp_path / "cache.db"),
        log_path=tmp_path / "log.jsonl",
    )

    result = asyncio.run(classifier.classify_sentence("Modern blues suggest a tech aesthetic."))

    assert result.epistemic_type == EpistemicType.OPINION
    assert provider.calls == 2


def test_classifier_defaults_to_factual_assertion_after_failures(tmp_path):
    provider = FakeProvider([ValueError("bad")] * 5)
    classifier = EpistemicClassifier(
        model="fake-model",
        provider=provider,
        cache=ClassificationCache(tmp_path / "cache.db"),
        log_path=tmp_path / "log.jsonl",
    )

    result = asyncio.run(classifier.classify_sentence("This cannot be classified."))

    assert result.epistemic_type == EpistemicType.FACTUAL_ASSERTION
    assert result.verifiability == Verifiability.VERIFIABLE
    assert result.confidence == 0.0
    assert provider.calls == 5


def test_prompt_contains_argumentative_debate_guidance():
    prompt = build_prompt("The leap from computation to experience is asserted, not explained.")

    assert "Argumentative debate handling" in prompt
    assert "Critique of an argument's explanatory structure" in prompt
    assert "Contested metaphysical stance" in prompt
