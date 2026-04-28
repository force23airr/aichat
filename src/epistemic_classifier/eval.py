from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .classifier import DEFAULT_MODEL, EpistemicClassifier
from .schema import EpistemicType


def _load_eval_set(eval_set_path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(eval_set_path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


async def run_eval_async(
    eval_set_path: str | Path,
    model: str = DEFAULT_MODEL,
    classifier: EpistemicClassifier | None = None,
    save_dir: str | Path = "eval_results",
) -> dict[str, Any]:
    rows = _load_eval_set(eval_set_path)
    classifier = classifier or EpistemicClassifier(model=model)
    predictions = await classifier.classify_many(
        [(row["sentence"], row.get("prior_sentence"), row.get("speaker")) for row in rows],
        concurrency=10,
    )

    strict_rows = [(row, pred) for row, pred in zip(rows, predictions) if not row.get("ambiguous")]
    total = len(strict_rows) or 1
    correct_type = 0
    errors: list[dict[str, Any]] = []
    labels = [item.value for item in EpistemicType]
    confusion: dict[str, dict[str, int]] = {gold: {pred: 0 for pred in labels} for gold in labels}
    counts = {label: {"tp": 0, "fp": 0, "fn": 0} for label in labels}

    subtype_total = 0
    subtype_correct = 0
    hedge_tp = hedge_fp = hedge_fn = 0

    for row, pred in strict_rows:
        gold = row["label"]
        gold_type = gold["epistemic_type"]
        pred_type = pred.epistemic_type.value
        confusion[gold_type][pred_type] += 1
        if pred_type == gold_type:
            correct_type += 1
            counts[gold_type]["tp"] += 1
        else:
            counts[pred_type]["fp"] += 1
            counts[gold_type]["fn"] += 1
            errors.append(
                {
                    "sentence": row["sentence"],
                    "predicted": pred_type,
                    "gold": gold_type,
                    "reasoning": pred.reasoning,
                }
            )

        if gold_type == "factual_assertion" and pred_type == "factual_assertion":
            subtype_total += 1
            pred_subtype = pred.subtype.value if pred.subtype else None
            if pred_subtype == gold.get("subtype"):
                subtype_correct += 1

        gold_hedges = set(gold.get("hedge_markers", []))
        pred_hedges = set(pred.hedge_markers)
        hedge_tp += len(gold_hedges & pred_hedges)
        hedge_fp += len(pred_hedges - gold_hedges)
        hedge_fn += len(gold_hedges - pred_hedges)

    per_class: dict[str, dict[str, float]] = {}
    for label, stat in counts.items():
        precision = stat["tp"] / (stat["tp"] + stat["fp"]) if stat["tp"] + stat["fp"] else 0.0
        recall = stat["tp"] / (stat["tp"] + stat["fn"]) if stat["tp"] + stat["fn"] else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
        }

    hedge_precision = hedge_tp / (hedge_tp + hedge_fp) if hedge_tp + hedge_fp else 0.0
    hedge_recall = hedge_tp / (hedge_tp + hedge_fn) if hedge_tp + hedge_fn else 0.0

    metrics: dict[str, Any] = {
        "model": model,
        "eval_set_path": str(eval_set_path),
        "total": len(rows),
        "ambiguous_skipped": len(rows) - len(strict_rows),
        "epistemic_type_accuracy": correct_type / total,
        "per_class_precision_recall": per_class,
        "subtype_accuracy_conditional": subtype_correct / subtype_total if subtype_total else 0.0,
        "hedge_detection_f1": _f1(hedge_precision, hedge_recall),
        "confusion_matrix": confusion,
        "errors": errors,
    }

    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = save_path / f"v1_{timestamp}.json"
    report_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    metrics["report_path"] = str(report_path)
    return metrics


def run_eval(
    eval_set_path: str | Path,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    import asyncio

    return asyncio.run(run_eval_async(eval_set_path=eval_set_path, model=model))
