from epistemic_classifier.cache import ClassificationCache
from epistemic_classifier.schema import Classification, EpistemicType, FactualSubtype, Verifiability


def test_cache_round_trip(tmp_path):
    cache = ClassificationCache(tmp_path / "cache.db")
    classification = Classification(
        sentence="The US GDP grew by 2.8% in Q4 2025.",
        epistemic_type=EpistemicType.FACTUAL_ASSERTION,
        verifiability=Verifiability.VERIFIABLE,
        subtype=FactualSubtype.NUMERIC_TEMPORAL,
        hedge_markers=[],
        confidence=0.97,
        reasoning="Specific numeric claim.",
    )

    cache.set("model-a", classification.sentence, None, classification)
    cached = cache.get("model-a", classification.sentence, None)

    assert cached == classification
    assert cache.get("model-b", classification.sentence, None) is None


def test_cache_invalidates_when_prompt_version_changes(tmp_path):
    cache = ClassificationCache(tmp_path / "cache.db")
    classification = Classification(
        sentence="What is your view?",
        epistemic_type=EpistemicType.QUESTION,
        verifiability=Verifiability.UNVERIFIABLE_IN_PRINCIPLE,
        subtype=None,
        hedge_markers=[],
        confidence=0.99,
        reasoning="Interrogative.",
    )

    cache.set("model-a", classification.sentence, None, classification, prompt_version="v1")

    assert cache.get("model-a", classification.sentence, None, prompt_version="v1") == classification
    assert cache.get("model-a", classification.sentence, None, prompt_version="v2") is None
