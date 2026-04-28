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
from .config import agents_from_participants, load_session_config
from .mcp_runtime import MCPRuntime, format_discovered_tools
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
    task_parser.add_argument("goal", nargs="?", help="The task or question for the models")
    task_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="YAML session config with named agents, roles, and models",
    )
    task_parser.add_argument(
        "--starter", default=None, help="Model or agent that starts the conversation (e.g., claude)"
    )
    task_parser.add_argument(
        "--participants",
        nargs="+",
        default=None,
        help="List of participant models (including the starter if it should speak again)",
    )
    task_parser.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Maximum number of turns (default: 8)",
    )
    task_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save transcript to a markdown file",
    )
    task_parser.add_argument(
        "--discover-tools",
        action="store_true",
        help="Connect to configured MCP servers and include discovered tools in agent prompts",
    )
    task_parser.add_argument(
        "--enable-tool-calls",
        action="store_true",
        help="Allow agents to execute assigned MCP tools during their turns",
    )
    task_parser.add_argument(
        "--max-tool-calls-per-turn",
        type=int,
        default=3,
        help="Maximum MCP tool calls one agent can make in a single turn (default: 3)",
    )

    mcp_parser = sub.add_parser("mcp", help="Inspect configured MCP servers")
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_command", required=True)
    mcp_list = mcp_sub.add_parser("list", help="List tools exposed by configured MCP servers")
    mcp_list.add_argument("--config", required=True, help="YAML session config")
    mcp_list.add_argument(
        "--server",
        action="append",
        default=None,
        help="Specific MCP server to inspect; can be repeated",
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
    elif args.command == "mcp":
        asyncio.run(run_mcp(args))
    elif args.command == "classify":
        run_classify(args)


async def run_task(args):
    session = _resolve_task_args(args)
    print(f"\n{CYAN}⚡ aichat — Collaborative AI session{RESET}")
    print(f"{CYAN}Task: {session['task']}{RESET}")
    print(f"{CYAN}Participants: {', '.join(session['participants'])}{RESET}\n")

    bridge = Bridge(
        task=session["task"],
        starter=session["starter"],
        participants=session["participants"],
        max_turns=session["max_turns"],
        agents=session["agents"],
        mcp_servers=session["mcp_servers"],
        discover_mcp_tools=args.discover_tools,
        enable_tool_calls=args.enable_tool_calls,
        max_tool_calls_per_turn=args.max_tool_calls_per_turn,
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


async def run_mcp(args):
    if args.mcp_command == "list":
        config = load_session_config(args.config)
        runtime = MCPRuntime(config.mcp_servers)
        tools = await runtime.list_tools(args.server)
        print(format_discovered_tools(tools))


def _resolve_task_args(args):
    config = load_session_config(args.config) if args.config else None

    task = args.goal or (config.task if config else None)
    if not task:
        raise SystemExit("Error: provide a task goal or set 'task' in the config file")

    if config:
        agents = config.agents
        mcp_servers = config.mcp_servers
        participants = config.participants
        starter = args.starter or config.starter or participants[0]
        max_turns = args.max_turns if args.max_turns is not None else (config.max_turns or 8)
    else:
        if not args.participants:
            raise SystemExit("Error: --participants is required when --config is not provided")
        participants = args.participants
        agents = agents_from_participants(participants)
        mcp_servers = {}
        starter = args.starter
        max_turns = args.max_turns or 8

    if not starter:
        raise SystemExit("Error: --starter is required when --config does not define starter")
    if starter not in participants:
        raise SystemExit(f"Error: starter '{starter}' must be one of: {', '.join(participants)}")

    return {
        "task": task,
        "starter": starter,
        "participants": participants,
        "max_turns": max_turns,
        "agents": agents,
        "mcp_servers": mcp_servers,
    }


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
