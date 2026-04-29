from pathlib import Path
from types import SimpleNamespace

import pytest

from aichat.main import _resolve_template_choice, run_init


def test_resolve_template_choice_handles_fresh_and_resume():
    assert _resolve_template_choice("codex-claude", SimpleNamespace(fresh=True, resume=False)) == "codex-claude-fresh"
    assert _resolve_template_choice("codex-claude", SimpleNamespace(fresh=False, resume=True)) == "codex-claude-resume"
    assert _resolve_template_choice("fusion-mcp", SimpleNamespace(fresh=False, resume=False)) == "fusion-mcp"


def test_resolve_template_choice_rejects_conflicting_flags():
    with pytest.raises(SystemExit):
        _resolve_template_choice("codex-claude", SimpleNamespace(fresh=True, resume=True))


def test_run_init_writes_fresh_template(tmp_path, capsys):
    output = tmp_path / "generated.yaml"
    args = SimpleNamespace(
        list=False,
        template="codex-claude",
        output=str(output),
        force=True,
        fresh=True,
        resume=False,
    )

    run_init(args)

    text = output.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert "Created" in captured.out
    assert "codex_local" in text
    assert "args: [\"exec\", \"-\"]" in text


def test_run_init_writes_resume_template(tmp_path, capsys):
    output = tmp_path / "generated.yaml"
    args = SimpleNamespace(
        list=False,
        template="codex-claude",
        output=str(output),
        force=True,
        fresh=False,
        resume=True,
    )

    run_init(args)

    text = output.read_text(encoding="utf-8")
    captured = capsys.readouterr()
    assert "Created" in captured.out
    assert "args: [\"exec\", \"resume\", \"--last\"]" in text
