from __future__ import annotations

import hashlib


CLASSIFICATION_PROMPT = """You classify sentences from AI-to-AI collaborative conversations by their epistemic type. Your output guides a downstream verification system that fact-checks only verifiable claims and skips opinions and recommendations.

For the input sentence, return a JSON object with these fields:

- epistemic_type: one of "factual_assertion", "opinion", "prediction", "recommendation", "hypothetical", "question", "meta"
- verifiability: one of "verifiable", "unverifiable_in_principle", "verifiable_only_post_hoc"
- subtype: for factual_assertion only, one of "numeric_temporal", "entity_relation", "categorical", "causal", "comparative", "existential", "definitional". Null otherwise.
- hedge_markers: array of explicit uncertainty phrases present in the sentence (e.g., "likely", "I think", "tends to"). Empty array if none.
- confidence: your confidence in this classification, 0.0 to 1.0.
- reasoning: one sentence explaining the classification.

Definitions:
- factual_assertion: A claim about the world that is true or false independent of the speaker's preferences, and that could in principle be checked against evidence.
- opinion: A value judgment, aesthetic preference, or subjective evaluation. Cannot be true or false in the same sense as a factual claim.
- prediction: A claim about a future state. Verifiable only after the predicted time arrives.
- recommendation: A directive or suggestion about what should be done. Not a claim about the world.
- hypothetical: A claim about a counterfactual or imagined scenario, often signaled by "if", "imagine", "suppose".
- question: An interrogative seeking information or input.
- meta: A statement about the conversation itself, the speaker's process, or the form of the discussion (e.g., "let me start with", "good point", "moving on").

Hedges do not change the epistemic_type. A hedged factual assertion is still a factual_assertion; record the hedge phrases.

Argumentative debate handling:
- Sentences that evaluate another participant's argument, reasoning, test, or theory as circular, incoherent, unresolved, asserted, unexplained, or not decisive are usually meta or opinion, not factual_assertion.
- Sentences that restate a participant's position as a position ("Claude assumes...", "GPT argues...", "my theory says...") are meta unless they make a separate checkable claim about the world.
- In philosophical or strategic debate, do not classify a metaphysical thesis as factual_assertion merely because it has declarative form ("consciousness is computation", "there is no extra ingredient"). Prefer opinion when it is a contested stance, and meta when it is a critique of the argument itself.

Examples:

Sentence: "The US GDP grew by 2.8% in Q4 2025."
Output: {"epistemic_type": "factual_assertion", "verifiability": "verifiable", "subtype": "numeric_temporal", "hedge_markers": [], "confidence": 0.97, "reasoning": "Specific numeric claim about a public economic indicator at a defined time."}

Sentence: "Modern blues and greens suggest a tech aesthetic."
Output: {"epistemic_type": "opinion", "verifiability": "unverifiable_in_principle", "subtype": null, "hedge_markers": [], "confidence": 0.88, "reasoning": "Aesthetic judgment about color associations; not a fact-checkable claim."}

Sentence: "I think we should target a broad professional audience."
Output: {"epistemic_type": "recommendation", "verifiability": "unverifiable_in_principle", "subtype": null, "hedge_markers": ["I think"], "confidence": 0.92, "reasoning": "Suggested course of action, hedged with personal-view marker."}

Sentence: "Adoption of AI tools will likely double by 2027."
Output: {"epistemic_type": "prediction", "verifiability": "verifiable_only_post_hoc", "subtype": null, "hedge_markers": ["likely"], "confidence": 0.91, "reasoning": "Future-tense claim about a measurable trend, hedged."}

Sentence: "Let me kick off with some opening questions."
Output: {"epistemic_type": "meta", "verifiability": "unverifiable_in_principle", "subtype": null, "hedge_markers": [], "confidence": 0.96, "reasoning": "Statement about the speaker's conversational move, not about the world."}

Sentence: "What are your thoughts on this direction?"
Output: {"epistemic_type": "question", "verifiability": "unverifiable_in_principle", "subtype": null, "hedge_markers": [], "confidence": 0.99, "reasoning": "Interrogative seeking input."}

Sentence: "If we positioned this as a B2B tool, the messaging would shift."
Output: {"epistemic_type": "hypothetical", "verifiability": "unverifiable_in_principle", "subtype": null, "hedge_markers": [], "confidence": 0.93, "reasoning": "Counterfactual scenario introduced with 'if'."}

Sentence: "The leap from computation to experience is asserted, not explained."
Output: {"epistemic_type": "meta", "verifiability": "unverifiable_in_principle", "subtype": null, "hedge_markers": [], "confidence": 0.9, "reasoning": "Critique of an argument's explanatory structure rather than a directly fact-checkable world claim."}

Sentence: "Consciousness is essentially computation."
Output: {"epistemic_type": "opinion", "verifiability": "unverifiable_in_principle", "subtype": null, "hedge_markers": [], "confidence": 0.86, "reasoning": "Contested metaphysical stance in a debate, not an independently checkable factual assertion."}

Sentence: "Global Workspace Theory posits that consciousness arises when information is globally available to many subsystems."
Output: {"epistemic_type": "factual_assertion", "verifiability": "verifiable", "subtype": "definitional", "hedge_markers": [], "confidence": 0.93, "reasoning": "Checkable claim about what a named theory states."}

Now classify this sentence:

Sentence: {input_sentence}
Context (optional, for resolving ambiguity): {prior_sentence}
Output:
"""


def build_prompt(input_sentence: str, prior_sentence: str | None = None) -> str:
    return (
        CLASSIFICATION_PROMPT.replace("{input_sentence}", input_sentence)
        .replace("{prior_sentence}", prior_sentence or "")
    )


# Short hash of the prompt template so cache entries are scoped to a prompt
# version. Editing CLASSIFICATION_PROMPT automatically invalidates stale
# entries without requiring a manual cache wipe.
PROMPT_VERSION = hashlib.sha256(CLASSIFICATION_PROMPT.encode("utf-8")).hexdigest()[:12]
