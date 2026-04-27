#!/usr/bin/env python3
"""
aichat — let your AI models talk to each other.

Usage:
    aichat task "Design a logo" --starter claude --participants claude gpt
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .bridge import Bridge

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

    args = parser.parse_args()

    if args.command == "task":
        asyncio.run(run_task(args))


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


if __name__ == "__main__":
    main()
