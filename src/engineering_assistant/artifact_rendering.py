"""Render every supported deliverable declared by an assignment plan."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import safe_relative
from .rendering import render_text_docx, render_text_pdf
from .xlsx_rendering import render_solution_xlsx


SUPPORTED_RENDER_FORMATS = {"pdf", "docx", "xlsx"}


def render_declared_artifacts(
    solution: dict[str, Any],
    plan: dict[str, Any],
    run_root: Path,
    *,
    identity: dict[str, Any] | None = None,
    style_profile: dict[str, Any] | None = None,
) -> list[Path]:
    """Render all declared artifacts after validating the whole declaration set."""
    if not isinstance(solution, dict) or not isinstance(plan, dict):
        raise ValueError("solution and plan must be objects")
    requested = plan.get("deliverables")
    if not isinstance(requested, list) or not requested:
        raise ValueError("assignment plan requires at least one deliverable")

    declarations: list[tuple[str, Path]] = []
    seen_paths: set[str] = set()
    for item in requested:
        if not isinstance(item, dict):
            raise ValueError("each deliverable declaration must be an object")
        relative = item.get("path")
        format_name = str(item.get("format", "")).casefold().lstrip(".")
        if not isinstance(relative, str) or not relative:
            raise ValueError("each deliverable needs a path")
        if format_name not in SUPPORTED_RENDER_FORMATS:
            raise ValueError(f"unsupported render format: {format_name or 'missing'}")
        if relative in seen_paths:
            raise ValueError(f"duplicate deliverable path: {relative}")
        seen_paths.add(relative)
        output = safe_relative(Path(run_root), relative)
        if output.suffix.casefold() != f".{format_name}":
            raise ValueError(f"deliverable extension does not match requested {format_name} format")
        declarations.append((format_name, output))

    rendered: list[Path] = []
    for format_name, output in declarations:
        if format_name == "pdf":
            render_text_pdf(solution, output, identity=identity, style_profile=style_profile)
        elif format_name == "docx":
            render_text_docx(solution, output, identity=identity, style_profile=style_profile)
        else:
            render_solution_xlsx(solution, output, include_identity_placeholders=True)
        rendered.append(output)
    return rendered


__all__ = ["SUPPORTED_RENDER_FORMATS", "render_declared_artifacts"]
