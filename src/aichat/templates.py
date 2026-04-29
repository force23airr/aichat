from __future__ import annotations

from importlib import resources
from pathlib import Path


TEMPLATE_NAMES = ("codex-claude", "ollama-codex", "fusion-mcp")


class TemplateError(ValueError):
    pass


def list_templates() -> tuple[str, ...]:
    return TEMPLATE_NAMES


def default_output_path(template_name: str) -> Path:
    _validate_template_name(template_name)
    return Path(f"aichat.{template_name}.yaml")


def render_template(template_name: str) -> str:
    _validate_template_name(template_name)
    template_file = resources.files("aichat").joinpath("templates", f"{template_name}.yaml")
    return template_file.read_text(encoding="utf-8")


def write_template(
    template_name: str,
    output_path: str | Path | None = None,
    *,
    force: bool = False,
) -> Path:
    target = Path(output_path) if output_path else default_output_path(template_name)
    target = target.expanduser()
    if target.exists() and not force:
        raise TemplateError(f"Refusing to overwrite existing file: {target}")
    target.write_text(render_template(template_name), encoding="utf-8")
    return target


def _validate_template_name(template_name: str) -> None:
    if template_name not in TEMPLATE_NAMES:
        raise TemplateError(
            f"Unknown template '{template_name}'. Available templates: {', '.join(TEMPLATE_NAMES)}"
        )
