import pytest

from aichat.config import load_session_config
from aichat.templates import TemplateError, list_templates, render_template, write_template


def test_all_templates_render_and_load(tmp_path):
    for name in list_templates():
        path = write_template(name, tmp_path / f"{name}.yaml")

        rendered = render_template(name)
        config = load_session_config(path)

        assert rendered.strip()
        assert config.agents
        assert config.task


def test_write_template_refuses_overwrite(tmp_path):
    path = tmp_path / "aichat.codex-claude.yaml"
    write_template("codex-claude", path)

    with pytest.raises(TemplateError, match="Refusing to overwrite"):
        write_template("codex-claude", path)


def test_write_template_force_overwrites(tmp_path):
    path = tmp_path / "aichat.codex-claude.yaml"
    path.write_text("old", encoding="utf-8")

    write_template("codex-claude", path, force=True)

    assert "codex_local" in path.read_text(encoding="utf-8")


def test_unknown_template_rejected(tmp_path):
    with pytest.raises(TemplateError, match="Unknown template"):
        write_template("missing", tmp_path / "missing.yaml")
