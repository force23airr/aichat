#!/usr/bin/env python3
"""
aichat — let your AI models talk to each other.

Usage:
    aichat task "Design a logo" --starter claude --participants claude gpt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .bridge import Bridge
from epistemic_classifier import DEFAULT_MODEL, classify_transcript

# Color helpers (no dependencies)
GREEN = "\033[92m"
CYAN = "\033[96m"
RESET = "\033[0m"


def main():
    parser = argparse.ArgumentParser(
        prog="aichat",
        description="Multi-model AI collaboration from your terminal.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    task_parser = sub.add_parser("task", help="Start a collaboration session")
    task_parser.add_argument("goal", help="The task or question for the models")
    task_parser.add_argument(
        "--starter", required=True, help="Model that starts the conversation (e.g., claude)"
    )
    task_parser.add_argument(
        "--participants",
        nargs="+",
        required=True,
        help="List of participant models (including the starter if it should speak again)",
    )
    task_parser.add_argument(
        "--max-turns",
        type=int,
        default=8,
        help="Maximum number of turns (default: 8)",
    )
    task_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save transcript to a markdown file",
    )

    classify_parser = sub.add_parser("classify", help="Classify transcript sentences by epistemic type")
    classify_parser.add_argument("transcript", help="Path to an aichat transcript")
    classify_parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Classifier model (default: {DEFAULT_MODEL})",
    )
    classify_parser.add_argument(
        "--output",
        default=None,
        help="Output JSONL path (default: <transcript>.classified.jsonl)",
    )
    classify_parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Parallel classification calls (default: 4; raise on higher API tiers)",
    )

    args = parser.parse_args()

    if args.command == "task":
        asyncio.run(run_task(args))
    elif args.command == "classify":
        run_classify(args)


async def run_task(args):
    print(f"\n{CYAN}⚡ aichat — Collaborative AI session{RESET}")
    print(f"{CYAN}Task: {args.goal}{RESET}")
    print(f"{CYAN}Participants: {', '.join(args.participants)}{RESET}\n")

    bridge = Bridge(
        task=args.goal,
        starter=args.starter,
        participants=args.participants,
        max_turns=args.max_turns,
    )

    try:
        async for speaker, message in bridge.stream():
            print(f"{GREEN}[{speaker}]{RESET} {message}\n")
    except KeyboardInterrupt:
        print("\n\nSession interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        outpath = Path(args.output)
        bridge.transcript.save(str(outpath))
        print(f"Transcript saved to {outpath}")
    else:
        print(f"Session ended. {len(bridge.transcript.entries)} messages exchanged.")


def _classification_to_dict(result):
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return json.loads(result.json())


def run_classify(args):
    transcript_path = Path(args.transcript)
    results = classify_transcript(
        transcript_path=transcript_path,
        model=args.model,
        concurrency=args.concurrency,
    )
    output_path = Path(args.output) if args.output else transcript_path.with_suffix(
        transcript_path.suffix + ".classified.jsonl"
    )

    counts: dict[str, int] = {}
    failed: dict[str, int] = {}
    low_conf: dict[str, int] = {}
    with output_path.open("w", encoding="utf-8") as handle:
        for result in results:
            payload = _classification_to_dict(result)
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            label = result.classification.epistemic_type.value
            counts[label] = counts.get(label, 0) + 1
            conf = result.classification.confidence
            # confidence == 0.0 is the fallback used when the classifier
            # exhausted retries — those bias the factual_assertion bucket
            # and deserve a separate count in the summary.
            if conf == 0.0:
                failed[label] = failed.get(label, 0) + 1
            elif conf < 0.5:
                low_conf[label] = low_conf.get(label, 0) + 1

    total_failed = sum(failed.values())
    print(f"Classified {len(results)} sentences")
    if total_failed:
        print(
            f"WARNING: {total_failed} classification(s) failed and defaulted "
            f"to factual_assertion (confidence=0.0). Treat counts accordingly."
        )
    print("Epistemic type summary:")
    for label, count in sorted(counts.items()):
        extras = []
        if label in failed:
            extras.append(f"{failed[label]} failed")
        if label in low_conf:
            extras.append(f"{low_conf[label]} low-conf")
        suffix = f"  ({', '.join(extras)})" if extras else ""
        print(f"  {label}: {count}{suffix}")
    print(f"Full classifications saved to {output_path}")


if __name__ == "__main__":
    main()
