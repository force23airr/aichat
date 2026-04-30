"""Interactive session wizard for `aichat new`.

This module is split into two layers:

- The **builder layer** is pure-Python, has no `questionary` import, and is
  the trust boundary that turns collected answers into a validated
  `SessionConfig` and YAML text. It is fully unit-tested.
- The **prompt layer** uses `questionary` (lazy imported) to collect answers
  and call into the builder layer. It is intentionally thin.

The builder layer must remain importable when `questionary` is not
installed.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from .config import AgentSpec, MCPServerSpec, SessionConfig
from .setup import (
    PROVIDER_ENV_VARS,
    command_status_for_agent,
    load_dotenv,
    provider_status,
    upsert_local_env,
)


# ---------------------------------------------------------------------------
# Builder layer (no questionary import; safe to import without optional dep)
# ---------------------------------------------------------------------------


WIZARD_API_PROVIDERS: tuple[str, ...] = (
    "claude",
    "gpt",
    "deepseek",
    "groq",
    "together",
    "perplexity",
    "gemini",
    "ollama",
)

KNOWN_CLI_AGENTS: dict[str, dict[str, object]] = {
    "codex": {
        "command": "codex",
        "args": ["exec", "-"],
        "default_role": "A local command-line coding assistant.",
    },
    "claude code": {
        "command": "claude",
        "args": ["--print"],
        "default_role": "A local Claude Code assistant for the current project.",
    },
    "ollama (as CLI)": {
        "command": "ollama",
        "args": ["run", "{model}", "{prompt}"],
        "default_role": "A local Ollama model used as a CLI participant.",
        "model_prompt": "Ollama model to use (e.g. gemma3:e2b, llama3.1:8b):",
    },
}

DEFAULT_ROLE_SUGGESTIONS = (
    "Coordinate the collaboration and break the task into steps.",
    "Challenge weak assumptions and identify risks.",
    "Gather evidence and propose options.",
    "Propose concrete next actions and validate them.",
)

MAX_TURNS_CEILING = 50

AGENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class WizardError(ValueError):
    """Raised when the wizard receives an invalid answer set."""


@dataclass
class AgentAnswer:
    """One agent's worth of wizard answers, before turning into AgentSpec."""

    name: str
    kind: str  # "api" or "command"
    role: str = ""

    # API path
    provider: str | None = None

    # Command path
    command: str | None = None
    command_args: list[str] = field(default_factory=list)
    command_env: dict[str, str] = field(default_factory=dict)
    command_cwd: str | None = None
    command_timeout: int = 120


@dataclass
class WizardAnswers:
    """The full collected answer set. The trust boundary for the builder."""

    task: str
    agents: list[AgentAnswer]
    starter: str
    max_turns: int
    output_path: Path


def build_session_config(answers: WizardAnswers) -> SessionConfig:
    """Validate answers and produce a SessionConfig.

    Raises WizardError on any validation failure so the prompt layer can
    re-prompt without crashing.
    """
    if not answers.task or not answers.task.strip():
        raise WizardError("Task is required")
    if not answers.agents:
        raise WizardError("At least one agent is required")
    if answers.max_turns < 1:
        raise WizardError("max_turns must be at least 1")
    if answers.max_turns > MAX_TURNS_CEILING:
        raise WizardError(f"max_turns must be at most {MAX_TURNS_CEILING}")

    names = [agent.name for agent in answers.agents]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise WizardError(f"Duplicate agent names: {', '.join(duplicates)}")

    for name in names:
        if not AGENT_NAME_PATTERN.match(name):
            raise WizardError(
                f"Agent name '{name}' must start with a lowercase letter and contain only "
                "lowercase letters, digits, or underscores"
            )

    if answers.starter not in names:
        raise WizardError(
            f"Starter '{answers.starter}' must be one of the agent names: {', '.join(names)}"
        )

    agent_specs = [_agent_answer_to_spec(agent) for agent in answers.agents]

    return SessionConfig(
        task=answers.task.strip(),
        starter=answers.starter,
        max_turns=answers.max_turns,
        mcp_servers={},
        agents=agent_specs,
    )


def _agent_answer_to_spec(answer: AgentAnswer) -> AgentSpec:
    if answer.kind == "api":
        if not answer.provider:
            raise WizardError(f"Agent '{answer.name}' is missing a provider")
        return AgentSpec(
            name=answer.name,
            model=answer.provider,
            role=answer.role.strip(),
        )

    if answer.kind == "command":
        if not answer.command:
            raise WizardError(f"Agent '{answer.name}' is missing a command")
        cwd_path: Path | None = Path(answer.command_cwd) if answer.command_cwd else None
        return AgentSpec(
            name=answer.name,
            model=f"command:{answer.command}",
            provider="command",
            role=answer.role.strip(),
            command=answer.command,
            command_args=list(answer.command_args),
            command_env=dict(answer.command_env),
            command_timeout=answer.command_timeout,
            command_cwd=cwd_path,
        )

    raise WizardError(f"Agent '{answer.name}' has unknown kind '{answer.kind}'")


def serialize_session_yaml(config: SessionConfig) -> str:
    """Serialize a SessionConfig into a clean, template-shaped YAML string.

    Strips fields at their defaults to keep output readable, and converts
    Path objects to strings (yaml.safe_dump cannot dump PosixPath).
    """
    payload: dict[str, object] = {}
    if config.task is not None:
        payload["task"] = config.task
    if config.starter is not None:
        payload["starter"] = config.starter
    if config.max_turns is not None:
        payload["max_turns"] = config.max_turns

    if config.mcp_servers:
        payload["mcp_servers"] = {
            name: _mcp_to_dict(server) for name, server in config.mcp_servers.items()
        }

    payload["agents"] = [_agent_to_dict(agent) for agent in config.agents]

    return yaml.safe_dump(payload, sort_keys=False)


def _agent_to_dict(agent: AgentSpec) -> dict[str, object]:
    out: dict[str, object] = {
        "name": agent.name,
        "model": agent.model,
    }
    if agent.provider:
        out["provider"] = agent.provider
    if agent.role:
        out["role"] = agent.role
    if agent.mcp_servers:
        out["mcp_servers"] = list(agent.mcp_servers)
    if agent.command:
        out["command"] = agent.command
    if agent.command_args:
        out["args"] = list(agent.command_args)
    if agent.command_env:
        out["env"] = dict(agent.command_env)
    if agent.command_timeout != 120:
        out["timeout"] = agent.command_timeout
    if agent.command_cwd is not None:
        out["cwd"] = str(agent.command_cwd)
    return out


def _mcp_to_dict(server: MCPServerSpec) -> dict[str, object]:
    out: dict[str, object] = {"command": server.command}
    if server.args:
        out["args"] = list(server.args)
    if server.env:
        out["env"] = dict(server.env)
    if server.allowed_tools:
        out["allowed_tools"] = list(server.allowed_tools)
    if server.description:
        out["description"] = server.description
    return out


# ---------------------------------------------------------------------------
# Doctor pre-flight (uses existing setup helpers, no questionary)
# ---------------------------------------------------------------------------


@dataclass
class DoctorIssue:
    label: str
    detail: str


def doctor_preflight(config: SessionConfig) -> list[DoctorIssue]:
    """Return a list of readiness issues for the given session config.

    Empty list = ready to run.
    """
    issues: list[DoctorIssue] = []
    seen_providers: set[str] = set()
    for agent in config.agents:
        provider = agent.provider_alias
        if provider in seen_providers:
            continue
        seen_providers.add(provider)
        status = provider_status(provider)
        if not status.configured:
            issues.append(DoctorIssue(label=f"provider {provider}", detail=status.detail))
    for agent in config.agents:
        cmd_status = command_status_for_agent(agent)
        if cmd_status and not cmd_status.configured:
            issues.append(
                DoctorIssue(label=f"agent {cmd_status.agent}", detail=cmd_status.detail)
            )
    return issues


# ---------------------------------------------------------------------------
# Prompt layer (questionary required)
# ---------------------------------------------------------------------------


WIZARD_INSTALL_HINT = (
    "The wizard needs the optional `questionary` dependency.\n"
    "Install it with:  pip install 'aichat[wizard]'"
)


def _require_questionary():
    try:
        import questionary  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised via run_new gate
        raise ImportError(WIZARD_INSTALL_HINT) from exc
    return questionary


def run_wizard(*, output_default: Path | None = None, force: bool = False) -> tuple[Path, SessionConfig]:
    """Run the interactive wizard. Returns (saved_path, session_config).

    Raises ImportError with a friendly hint if `questionary` is missing.
    Raises KeyboardInterrupt if the user cancels.
    """
    questionary = _require_questionary()

    print("aichat new — let's build a session.\n")
    answers = _collect_answers(questionary, output_default=output_default, force=force)
    config = build_session_config(answers)
    yaml_text = serialize_session_yaml(config)
    _print_yaml_preview(yaml_text)

    if not questionary.confirm("Looks good?", default=True).unsafe_ask():
        raise KeyboardInterrupt("User declined to save the generated config.")

    answers.output_path.write_text(yaml_text, encoding="utf-8")
    return answers.output_path, config


def _collect_answers(questionary, *, output_default: Path | None, force: bool) -> WizardAnswers:
    task = _prompt_required_text(questionary, "What should the agents work on?")

    n_agents = _prompt_number_of_agents(questionary)
    agents: list[AgentAnswer] = []
    used_names: set[str] = set()
    for index in range(n_agents):
        agents.append(_prompt_agent(questionary, index=index, used_names=used_names))
        used_names.add(agents[-1].name)

    starter = questionary.select(
        "Which agent starts?",
        choices=[a.name for a in agents],
        default=agents[0].name,
    ).unsafe_ask()

    max_turns_raw = questionary.text(
        f"Max turns (1-{MAX_TURNS_CEILING}):",
        default="6",
        validate=_validate_max_turns,
    ).unsafe_ask()
    max_turns = int(max_turns_raw)

    default_path = output_default or Path("aichat.session.yaml")
    output_path_raw = questionary.text(
        "Save as:",
        default=str(default_path),
    ).unsafe_ask()
    output_path = Path(output_path_raw).expanduser()
    if output_path.exists() and not force:
        if not questionary.confirm(
            f"{output_path} already exists. Overwrite?", default=False
        ).unsafe_ask():
            raise KeyboardInterrupt("User declined to overwrite existing file.")

    return WizardAnswers(
        task=task,
        agents=agents,
        starter=starter,
        max_turns=max_turns,
        output_path=output_path,
    )


def _prompt_required_text(questionary, prompt: str) -> str:
    return questionary.text(prompt, validate=lambda v: bool(v.strip()) or "Required").unsafe_ask().strip()


def _prompt_number_of_agents(questionary) -> int:
    choice = questionary.select(
        "How many agents?",
        choices=["2 (default)", "3", "4", "5", "Other..."],
        default="2 (default)",
    ).unsafe_ask()
    if choice == "Other...":
        raw = questionary.text(
            "Number of agents (1-10):",
            validate=lambda v: (v.isdigit() and 1 <= int(v) <= 10) or "Enter 1-10",
        ).unsafe_ask()
        return int(raw)
    return int(choice.split()[0])


def _prompt_agent(questionary, *, index: int, used_names: set[str]) -> AgentAnswer:
    print()
    print(f"Agent {index + 1}")
    kind_choice = questionary.select(
        f"Agent {index + 1} type?",
        choices=[
            "API model (Claude, GPT, Ollama, ...)",
            "Local CLI (codex, claude code, custom)",
        ],
    ).unsafe_ask()

    if kind_choice.startswith("API model"):
        return _prompt_api_agent(questionary, index=index, used_names=used_names)
    return _prompt_command_agent(questionary, index=index, used_names=used_names)


def _prompt_api_agent(questionary, *, index: int, used_names: set[str]) -> AgentAnswer:
    choices = []
    for provider in WIZARD_API_PROVIDERS:
        status = provider_status(provider)
        marker = "✓ ready" if status.configured else f"✗ {status.detail}"
        choices.append(f"{provider}  ({marker})")

    selection = questionary.select(
        "Pick a model provider:",
        choices=choices,
    ).unsafe_ask()
    provider = selection.split()[0]

    status = provider_status(provider)
    if not status.configured and provider in PROVIDER_ENV_VARS:
        env_var = PROVIDER_ENV_VARS[provider]
        if questionary.confirm(
            f"{provider} is not configured (needs {env_var}). Set it now?",
            default=True,
        ).unsafe_ask():
            key = questionary.password(f"Paste your {env_var}:").unsafe_ask()
            if key.strip():
                upsert_local_env(env_var, key.strip())
                load_dotenv()
                print(f"Saved {env_var} to .env")

    default_name = _suggest_agent_name(provider, used_names)
    name = _prompt_agent_name(questionary, default=default_name, used_names=used_names)
    role = questionary.text(
        f"Role for {name}?",
        default=DEFAULT_ROLE_SUGGESTIONS[index % len(DEFAULT_ROLE_SUGGESTIONS)],
    ).unsafe_ask()

    return AgentAnswer(
        name=name,
        kind="api",
        role=role,
        provider=provider,
    )


def _prompt_command_agent(questionary, *, index: int, used_names: set[str]) -> AgentAnswer:
    cli_choice = questionary.select(
        "Which CLI?",
        choices=list(KNOWN_CLI_AGENTS.keys()) + ["custom command"],
    ).unsafe_ask()

    if cli_choice == "custom command":
        command = questionary.text(
            "Command (binary on PATH):",
            validate=lambda v: bool(v.strip()) or "Required",
        ).unsafe_ask().strip()
        args_raw = questionary.text(
            "Args (space-separated, use {prompt} as a placeholder if needed):",
            default="",
        ).unsafe_ask()
        args = args_raw.split() if args_raw.strip() else []
        default_role = "A local command-line participant."
    else:
        preset = KNOWN_CLI_AGENTS[cli_choice]
        command = str(preset["command"])
        args = list(preset["args"])  # type: ignore[arg-type]
        default_role = str(preset["default_role"])

        if "model_prompt" in preset:
            model_name = questionary.text(
                str(preset["model_prompt"]),
                validate=lambda v: bool(v.strip()) or "Required",
            ).unsafe_ask().strip()
            args = _substitute_model_placeholder(args, model_name)

    if not shutil.which(command):
        print(f"Warning: '{command}' was not found on PATH.")
        if not questionary.confirm("Continue anyway?", default=False).unsafe_ask():
            return _prompt_command_agent(questionary, index=index, used_names=used_names)

    cwd_raw = questionary.text(
        "Working directory (relative to the saved YAML):",
        default=".",
    ).unsafe_ask()

    timeout_raw = questionary.text(
        "Command timeout in seconds:",
        default="120",
        validate=lambda v: (v.isdigit() and int(v) > 0) or "Must be a positive integer",
    ).unsafe_ask()

    default_name = _suggest_agent_name(command, used_names)
    name = _prompt_agent_name(questionary, default=default_name, used_names=used_names)
    role = questionary.text(f"Role for {name}?", default=default_role).unsafe_ask()

    return AgentAnswer(
        name=name,
        kind="command",
        role=role,
        command=command,
        command_args=args,
        command_cwd=cwd_raw or None,
        command_timeout=int(timeout_raw),
    )


def _prompt_agent_name(questionary, *, default: str, used_names: set[str]) -> str:
    def validator(value: str) -> bool | str:
        if not AGENT_NAME_PATTERN.match(value):
            return "Use lowercase letters, digits, or underscores; start with a letter."
        if value in used_names:
            return f"'{value}' is already used by another agent."
        return True

    return questionary.text(
        "Agent name:",
        default=default,
        validate=validator,
    ).unsafe_ask()


def _suggest_agent_name(stem: str, used_names: Iterable[str]) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", stem.lower()) or "agent"
    if not base[0].isalpha():
        base = f"a_{base}"
    candidate = base
    used = set(used_names)
    counter = 2
    while candidate in used:
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _substitute_model_placeholder(args: list[str], model_name: str) -> list[str]:
    """Replace any '{model}' token in args with the supplied model name."""
    return [model_name if arg == "{model}" else arg for arg in args]


def _validate_max_turns(value: str) -> bool | str:
    if not value.isdigit():
        return "Enter a positive integer."
    n = int(value)
    if n < 1:
        return "max_turns must be at least 1."
    if n > MAX_TURNS_CEILING:
        return f"max_turns must be at most {MAX_TURNS_CEILING}."
    return True


def _print_yaml_preview(yaml_text: str) -> None:
    print()
    print("\033[96m--- Generated session config ---\033[0m")
    print(yaml_text.rstrip())
    print("\033[96m--------------------------------\033[0m")
    print()


def print_doctor_preflight(issues: list[DoctorIssue]) -> bool:
    """Print pre-flight results. Returns True if everything is ready."""
    print()
    print("\033[96m--- Pre-flight check ---\033[0m")
    if not issues:
        print("All providers and commands are ready.")
        print("\033[96m------------------------\033[0m")
        return True
    for issue in issues:
        print(f"  ✗ {issue.label}: {issue.detail}")
    print("\033[96m------------------------\033[0m")
    return False
