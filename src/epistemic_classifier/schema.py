from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EpistemicType(str, Enum):
    FACTUAL_ASSERTION = "factual_assertion"
    OPINION = "opinion"
    PREDICTION = "prediction"
    RECOMMENDATION = "recommendation"
    HYPOTHETICAL = "hypothetical"
    QUESTION = "question"
    META = "meta"


class Verifiability(str, Enum):
    VERIFIABLE = "verifiable"
    UNVERIFIABLE_IN_PRINCIPLE = "unverifiable_in_principle"
    VERIFIABLE_ONLY_POST_HOC = "verifiable_only_post_hoc"


class FactualSubtype(str, Enum):
    NUMERIC_TEMPORAL = "numeric_temporal"
    ENTITY_RELATION = "entity_relation"
    CATEGORICAL = "categorical"
    CAUSAL = "causal"
    COMPARATIVE = "comparative"
    EXISTENTIAL = "existential"
    DEFINITIONAL = "definitional"


class Classification(BaseModel):
    sentence: str
    epistemic_type: EpistemicType
    verifiability: Verifiability
    subtype: Optional[FactualSubtype] = None
    hedge_markers: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class TranscriptClassification(BaseModel):
    speaker: str | None = None
    sentence_index: int
    classification: Classification
