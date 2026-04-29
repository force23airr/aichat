#!/usr/bin/env python3
"""
aichat — let your AI models talk to each other.

Usage:
    aichat task "Design a logo" --starter claude --participants claude gpt
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from pathlib import Path

from .bridge import Bridge
from .config import agents_from_participants, load_session_config
from .mcp_runtime import (
    DiscoveredTool,
    MCPRuntime,
    MCPRuntimeError,
    ToolCall,
    ToolCallParseError,
    format_discovered_tools,
    format_tool_result,
    mcp_sdk_available,
    validate_arguments,
)
from .relay import RelayDecision, RelayRequest
from .setup import (
    CONFIG_PATH,
    PROVIDER_ENV_VARS,
    command_statuses_for_agents,
    load_dotenv,
    provider_status,
    providers_for_agents,
    update_provider_config,
)
from .templates import TemplateError, default_output_path, list_templates, write_template
from epistemic_classifier import DEFAULT_MODEL, classify_transcript

# Color helpers (no dependencies)
GREEN = "\033[92m"
CYAN = "\033[96m"
RESET = "\033[0m"


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(
        prog="aichat",
        description="Multi-model AI collaboration from your terminal.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="Create a ready-to-run agent config from a template")
    init_parser.add_argument(
        "template",
        nargs="?",
        choices=list_templates(),
        help="Template to create",
    )
    init_parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output config path (default: aichat.<template>.yaml)",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists",
    )
    init_parser.add_argument(
        "--list",
        action="store_true",
        help="List available templates",
    )

    setup_parser = sub.add_parser("setup", help="Configure provider keys and local models")
    setup_parser.add_argument(
        "--provider",
        action="append",
        choices=["claude", "openai", "deepseek", "google", "groq", "ollama"],
        help="Provider to configure; can be repeated. Interactive if omitted.",
    )

    doctor_parser = sub.add_parser("doctor", help="Check local aichat provider setup")
    doctor_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Optional session config to check required agent providers",
    )

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
    task_parser.add_argument(
        "--human-relay",
        action="store_true",
        help="Pause for human approval when an agent proposes a relay message",
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
    mcp_call = mcp_sub.add_parser("call", help="Call one configured MCP tool directly")
    mcp_call.add_argument("--config", required=True, help="YAML session config")
    mcp_call.add_argument("--server", required=True, help="Configured MCP server name")
    mcp_call.add_argument("--tool", required=True, help="Tool name to call")
    mcp_call.add_argument(
        "--arguments",
        default="{}",
        help='JSON object passed as tool arguments, e.g. \'{"path":"README.md"}\'',
    )
    mcp_call.add_argument(
        "--json",
        action="store_true",
        help="Print the full tool result as JSON",
    )
    mcp_doctor = mcp_sub.add_parser("doctor", help="Check MCP SDK and configured servers")
    mcp_doctor.add_argument("--config", required=True, help="YAML session config")

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
    elif args.command == "init":
        run_init(args)
    elif args.command == "setup":
        run_setup(args)
    elif args.command == "doctor":
        run_doctor(args)
    elif args.command == "mcp":
        try:
            asyncio.run(run_mcp(args))
        except (MCPRuntimeError, ToolCallParseError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
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
        human_relay=args.human_relay,
        relay_approver=_approve_relay_cli if args.human_relay else None,
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


def run_init(args) -> None:
    if args.list:
        print("Available templates:")
        for name in list_templates():
            print(f"  - {name}")
        return
    if not args.template:
        print("Error: provide a template name or use `aichat init --list`.", file=sys.stderr)
        raise SystemExit(2)
    try:
        output_path = write_template(args.template, args.output, force=args.force)
    except TemplateError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(f"Created {output_path}")
    print("")
    print("Next:")
    print(f"  aichat doctor --config {output_path}")
    print(f"  aichat task --config {output_path}")
    if args.template == "fusion-mcp":
        print("")
        print("Edit the fusion MCP server command/args before running if your server name differs.")


async def _approve_relay_cli(speaker: str, request: RelayRequest) -> RelayDecision:
    print(f"\n{CYAN}Relay approval requested{RESET}")
    print(f"From: {speaker}")
    print(f"To: {request.target}")
    if request.reason:
        print(f"Reason: {request.reason}")
    print("\nProposed message:")
    print(request.message)
    print(
        "\nChoose: "
        "[1] send as-is  "
        "[2] edit before sending  "
        "[3] ask for clarification  "
        "[4] reject"
    )

    while True:
        choice = (await asyncio.to_thread(input, "relay> ")).strip().lower()
        if choice in ("1", "send", "s"):
            return RelayDecision(action="send", message=request.message)
        if choice in ("2", "edit", "e"):
            edited = await asyncio.to_thread(input, "edited message> ")
            message = edited.strip() or request.message
            return RelayDecision(action="send", message=message, note="Human edited before sending.")
        if choice in ("3", "clarify", "c"):
            prompt = await asyncio.to_thread(input, "clarification request> ")
            return RelayDecision(
                action="clarify",
                message=prompt.strip() or "Please clarify why this relay should be sent.",
            )
        if choice in ("4", "reject", "r", "no", "n"):
            note = await asyncio.to_thread(input, "rejection note> ")
            return RelayDecision(action="reject", note=note.strip())
        print("Choose 1, 2, 3, or 4.")


async def run_mcp(args):
    config = load_session_config(args.config)
    runtime = MCPRuntime(config.mcp_servers)
    if args.mcp_command == "list":
        tools = await runtime.list_tools(args.server)
        print(format_discovered_tools(tools))
    elif args.mcp_command == "call":
        arguments = _parse_json_object(args.arguments, "--arguments")
        tools = await runtime.list_tools([args.server])
        discovered = _find_discovered_tool(tools.get(args.server, []), args.tool)
        if discovered is None:
            raise SystemExit(f"Error: tool '{args.server}.{args.tool}' was not discovered or is not allowed")
        validate_arguments(discovered.input_schema, arguments)
        result = await runtime.call_tool(
            ToolCall(server=args.server, tool=args.tool, arguments=arguments)
        )
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, sort_keys=True))
        else:
            print(format_tool_result(result))
        if not result.ok:
            raise SystemExit(1)
    elif args.mcp_command == "doctor":
        ok = await _run_mcp_doctor(runtime)
        if not ok:
            raise SystemExit(1)


def _parse_json_object(raw: str, label: str) -> dict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Error: {label} must be valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Error: {label} must be a JSON object")
    return value


def _find_discovered_tool(tools: list[DiscoveredTool], name: str) -> DiscoveredTool | None:
    for tool in tools:
        if tool.name == name:
            return tool
    return None


async def _run_mcp_doctor(runtime: MCPRuntime) -> bool:
    print(f"MCP SDK: {'installed' if mcp_sdk_available() else 'missing'}")
    if not mcp_sdk_available():
        print("Install with: pip install -e '.[mcp]'")
        return False
    if not runtime.servers:
        print("Configured servers: none")
        return True

    ok = True
    print("Configured servers:")
    for name, server in sorted(runtime.servers.items()):
        allowed = ", ".join(server.allowed_tools) if server.allowed_tools else "all tools"
        print(f"  - {name}: {server.command} {' '.join(server.args)}")
        print(f"    allowed: {allowed}")
        try:
            tools = await runtime.list_server_tools(name)
        except MCPRuntimeError as exc:
            ok = False
            print(f"    status: error - {exc}")
            continue
        names = ", ".join(tool.name for tool in tools) if tools else "none"
        print("    status: ok")
        print(f"    discovered: {names}")
    return ok


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
        max_turns = args.max_turns if args.max_turns is not None else (
            config.max_turns if config.max_turns is not None else 8
        )
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

    _warn_missing_providers(agents)

    return {
        "task": task,
        "starter": starter,
        "participants": participants,
        "max_turns": max_turns,
        "agents": agents,
        "mcp_servers": mcp_servers,
    }


def run_setup(args) -> None:
    providers = args.provider or _prompt_setup_providers()
    for provider in providers:
        if provider == "ollama":
            update_provider_config("ollama", "")
            print("Configured ollama as a local provider. Make sure Ollama is running.")
            continue
        env_var = PROVIDER_ENV_VARS.get(provider)
        if not env_var:
            print(f"Skipping unknown provider: {provider}")
            continue
        key = getpass.getpass(f"{env_var}: ").strip()
        if key:
            os.environ[env_var] = key
            _upsert_local_env(env_var, key)
        update_provider_config(provider, env_var)
        if provider == "openai":
            update_provider_config("gpt", env_var)
        if provider == "claude":
            update_provider_config("anthropic", env_var)
        print(f"Configured {provider} using {env_var}.")
    print(f"User config: {CONFIG_PATH}")


def run_doctor(args) -> None:
    load_dotenv()
    providers = ["claude", "gpt", "ollama"]
    command_statuses = []
    if args.config:
        config = load_session_config(args.config)
        providers = providers_for_agents(config.agents)
        command_statuses = command_statuses_for_agents(config.agents)
    ok = True
    print("aichat provider setup:")
    for provider in providers:
        status = provider_status(provider)
        marker = "ok" if status.configured else "missing"
        print(f"  - {provider}: {marker} ({status.detail})")
        ok = ok and status.configured
    if command_statuses:
        print("command-backed agents:")
        for status in command_statuses:
            marker = "ok" if status.configured else "missing"
            print(f"  - {status.agent}: {marker} ({status.detail})")
            ok = ok and status.configured
    if not ok:
        print("Fix missing provider keys with `aichat setup` or .env, and install any missing local commands.")
        raise SystemExit(1)


def _prompt_setup_providers() -> list[str]:
    print("Select providers to configure. Press enter to skip a provider.")
    selected = []
    for provider in ("claude", "openai", "deepseek", "google", "groq", "ollama"):
        answer = input(f"Configure {provider}? [y/N] ").strip().lower()
        if answer in ("y", "yes"):
            selected.append(provider)
    return selected


def _upsert_local_env(key: str, value: str) -> None:
    env_path = Path(".env")
    lines = []
    found = False
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}="):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _warn_missing_providers(agents) -> None:
    missing = []
    for provider in providers_for_agents(agents):
        status = provider_status(provider)
        if not status.configured:
            missing.append(f"{provider} ({status.detail})")
    for status in command_statuses_for_agents(agents):
        if not status.configured:
            missing.append(f"{status.agent} command ({status.detail})")
    if missing:
        print(
            "Provider setup warning: "
            + ", ".join(missing)
            + ". Run `aichat setup` or use `aichat doctor --config <file>`.",
            file=sys.stderr,
        )


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
