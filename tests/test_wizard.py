"""Tests for the aichat wizard.

These tests target the builder layer of the wizard, which is intentionally
free of any `questionary` import so the suite runs without the optional
dependency installed.
"""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from aichat.config import load_session_config
from aichat.wizard import (
    AgentAnswer,
    DoctorIssue,
    KNOWN_CLI_AGENTS,
    MAX_TURNS_CEILING,
    WIZARD_INSTALL_HINT,
    WizardAnswers,
    WizardError,
    _substitute_model_placeholder,
    build_session_config,
    doctor_preflight,
    print_doctor_preflight,
    serialize_session_yaml,
)


def _api_answer(name: str, provider: str = "claude", role: str = "Help.") -> AgentAnswer:
    return AgentAnswer(name=name, kind="api", provider=provider, role=role)


def _command_answer(
    name: str,
    command: str = "codex",
    cwd: str | None = None,
    role: str = "Local CLI agent.",
) -> AgentAnswer:
    return AgentAnswer(
        name=name,
        kind="command",
        command=command,
        command_args=["exec", "-"],
        command_cwd=cwd,
        role=role,
    )


def test_builder_produces_loadable_yaml(tmp_path):
    answers = WizardAnswers(
        task="Build a thing",
        agents=[_api_answer("planner", "claude"), _api_answer("critic", "gpt")],
        starter="planner",
        max_turns=4,
        output_path=tmp_path / "session.yaml",
    )

    config = build_session_config(answers)
    yaml_text = serialize_session_yaml(config)

    output_file = tmp_path / "session.yaml"
    output_file.write_text(yaml_text, encoding="utf-8")
    parsed = load_session_config(output_file)

    assert parsed.task == "Build a thing"
    assert parsed.starter == "planner"
    assert parsed.max_turns == 4
    assert [a.name for a in parsed.agents] == ["planner", "critic"]
    assert parsed.agents[0].model == "claude"
    assert parsed.agents[1].model == "gpt"


def test_builder_rejects_duplicate_agent_names(tmp_path):
    answers = WizardAnswers(
        task="x",
        agents=[_api_answer("planner"), _api_answer("planner", provider="gpt")],
        starter="planner",
        max_turns=2,
        output_path=tmp_path / "x.yaml",
    )

    with pytest.raises(WizardError, match="Duplicate agent names"):
        build_session_config(answers)


def test_builder_rejects_starter_not_in_agents(tmp_path):
    answers = WizardAnswers(
        task="x",
        agents=[_api_answer("planner"), _api_answer("critic", provider="gpt")],
        starter="nobody",
        max_turns=2,
        output_path=tmp_path / "x.yaml",
    )

    with pytest.raises(WizardError, match="Starter 'nobody' must be one of"):
        build_session_config(answers)


def test_builder_rejects_invalid_agent_name(tmp_path):
    answers = WizardAnswers(
        task="x",
        agents=[_api_answer("Bad-Name")],
        starter="Bad-Name",
        max_turns=2,
        output_path=tmp_path / "x.yaml",
    )

    with pytest.raises(WizardError, match="must start with a lowercase letter"):
        build_session_config(answers)


def test_builder_enforces_max_turns_bounds(tmp_path):
    base = dict(
        task="x",
        agents=[_api_answer("planner")],
        starter="planner",
        output_path=tmp_path / "x.yaml",
    )

    with pytest.raises(WizardError, match="at least 1"):
        build_session_config(WizardAnswers(max_turns=0, **base))

    with pytest.raises(WizardError, match="at most"):
        build_session_config(WizardAnswers(max_turns=MAX_TURNS_CEILING + 1, **base))


def test_builder_requires_task(tmp_path):
    answers = WizardAnswers(
        task="   ",
        agents=[_api_answer("planner")],
        starter="planner",
        max_turns=2,
        output_path=tmp_path / "x.yaml",
    )

    with pytest.raises(WizardError, match="Task is required"):
        build_session_config(answers)


def test_builder_requires_at_least_one_agent(tmp_path):
    answers = WizardAnswers(
        task="x",
        agents=[],
        starter="anything",
        max_turns=2,
        output_path=tmp_path / "x.yaml",
    )

    with pytest.raises(WizardError, match="At least one agent"):
        build_session_config(answers)


def test_command_agent_yaml_strips_path_objects(tmp_path):
    workdir = tmp_path / "project"
    workdir.mkdir()
    answers = WizardAnswers(
        task="x",
        agents=[
            _api_answer("planner"),
            _command_answer("codex_local", cwd=str(workdir)),
        ],
        starter="planner",
        max_turns=2,
        output_path=tmp_path / "session.yaml",
    )

    config = build_session_config(answers)
    yaml_text = serialize_session_yaml(config)

    # Command agent serialized with friendly key names
    assert "command: codex" in yaml_text
    assert "args:" in yaml_text
    assert f"cwd: {workdir}" in yaml_text
    # Path object becomes a plain string (yaml.safe_dump can't dump PosixPath)
    assert "PosixPath" not in yaml_text
    assert "!!python" not in yaml_text

    # And it round-trips through load_session_config
    output_file = tmp_path / "session.yaml"
    output_file.write_text(yaml_text, encoding="utf-8")
    parsed = load_session_config(output_file)
    assert parsed.agents[1].command == "codex"
    assert parsed.agents[1].command_args == ["exec", "-"]
    assert parsed.agents[1].command_cwd == workdir.resolve()


def test_serialize_omits_empty_optional_fields(tmp_path):
    answers = WizardAnswers(
        task="x",
        agents=[_api_answer("planner", role="")],  # empty role
        starter="planner",
        max_turns=2,
        output_path=tmp_path / "session.yaml",
    )

    yaml_text = serialize_session_yaml(build_session_config(answers))

    # No spurious null/empty fields cluttering the YAML
    assert "command:" not in yaml_text
    assert "role:" not in yaml_text
    assert "mcp_servers:" not in yaml_text


def test_doctor_preflight_returns_issues_for_unconfigured_provider(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    answers = WizardAnswers(
        task="x",
        agents=[_api_answer("planner", "claude"), _api_answer("critic", "gpt")],
        starter="planner",
        max_turns=2,
        output_path=tmp_path / "x.yaml",
    )
    config = build_session_config(answers)

    issues = doctor_preflight(config)
    labels = [i.label for i in issues]

    assert "provider claude" in labels
    assert "provider gpt" in labels


def test_doctor_preflight_clean_for_ollama(tmp_path):
    answers = WizardAnswers(
        task="x",
        agents=[_api_answer("planner", "ollama")],
        starter="planner",
        max_turns=2,
        output_path=tmp_path / "x.yaml",
    )
    config = build_session_config(answers)

    # ollama is treated as configured by provider_status (assumes daemon)
    assert doctor_preflight(config) == []


def test_print_doctor_preflight_returns_status(capsys):
    assert print_doctor_preflight([]) is True
    out = capsys.readouterr().out
    assert "Pre-flight check" in out
    assert "ready" in out

    assert print_doctor_preflight([DoctorIssue(label="provider claude", detail="missing")]) is False
    out = capsys.readouterr().out
    assert "provider claude" in out


def test_ollama_preset_prompts_for_model_and_substitutes_placeholder():
    preset = KNOWN_CLI_AGENTS["ollama (as CLI)"]

    # The preset must declare a model prompt and put {model} before {prompt}
    assert "model_prompt" in preset
    args = list(preset["args"])  # type: ignore[arg-type]
    assert args.index("{model}") < args.index("{prompt}")

    substituted = _substitute_model_placeholder(args, "gemma3:e2b")
    assert "{model}" not in substituted
    assert substituted == ["run", "gemma3:e2b", "{prompt}"]


def test_substitute_model_placeholder_is_noop_without_token():
    assert _substitute_model_placeholder(["exec", "-"], "anything") == ["exec", "-"]


def test_run_new_without_questionary_prints_friendly_message(monkeypatch, capsys):
    """If questionary isn't importable, run_new should exit 1 with the install hint."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "questionary":
            raise ImportError("No module named 'questionary'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    from aichat.main import run_new

    args = type(
        "Args",
        (),
        {"output": None, "force": False, "no_run": True},
    )()

    with pytest.raises(SystemExit) as exc:
        run_new(args)

    assert exc.value.code == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "questionary" in combined.lower() or "wizard" in combined.lower()
    # Verify the install hint constant is consistent
    assert "aichat[wizard]" in WIZARD_INSTALL_HINT
