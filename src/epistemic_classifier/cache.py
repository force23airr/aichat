from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

from .schema import Classification


DEFAULT_STATE_DIR = Path.home() / ".epistemic_classifier"
CACHE_PATH_ENV = "EPISTEMIC_CLASSIFIER_CACHE_DB"


def default_cache_path() -> Path:
    return Path(os.environ.get(CACHE_PATH_ENV, DEFAULT_STATE_DIR / "cache.db")).expanduser()


def cache_key(
    model: str,
    sentence: str,
    prior_sentence: str | None,
    prompt_version: str = "",
) -> str:
    payload = "\x1f".join([model, prompt_version, sentence, prior_sentence or ""])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _model_to_json(model: Classification) -> str:
    if hasattr(model, "model_dump_json"):
        return model.model_dump_json()
    return model.json()


def _model_from_json(payload: str) -> Classification:
    if hasattr(Classification, "model_validate_json"):
        return Classification.model_validate_json(payload)
    return Classification.parse_raw(payload)


class ClassificationCache:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path).expanduser() if path else default_cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS classifications (
                    key TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    sentence TEXT NOT NULL,
                    prior_sentence TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def get(
        self,
        model: str,
        sentence: str,
        prior_sentence: str | None = None,
        prompt_version: str = "",
    ) -> Classification | None:
        key = cache_key(model, sentence, prior_sentence, prompt_version)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM classifications WHERE key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        return _model_from_json(row[0])

    def set(
        self,
        model: str,
        sentence: str,
        prior_sentence: str | None,
        classification: Classification,
        prompt_version: str = "",
    ) -> None:
        key = cache_key(model, sentence, prior_sentence, prompt_version)
        payload = _model_to_json(classification)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO classifications
                    (key, model, sentence, prior_sentence, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (key, model, sentence, prior_sentence, payload),
            )

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM classifications")


def json_dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)
