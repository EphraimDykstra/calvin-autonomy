"""Read-only project setup diagnostics for student workspaces."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any


REQUIRED_MODULES = {
    "pypdf": "PDF ingestion",
    "openpyxl": "spreadsheet ingestion",
    "reportlab": "PDF rendering",
    "PIL": "image validation",
    "docx": "editable DOCX rendering",
}

# Every skill and agent `scripts/setup.py` installs.  A partially installed
# tree must not report ready: a missing skill is invisible until the host
# silently fails to find it mid-assignment.
MANAGED_SKILLS = (
    "build-course-profile",
    "complete-assignment",
    "ingest-course-materials",
    "manage-student-memory",
    "schoolwork",
    "setup-student-workspace",
    "verify-assignment",
)
MANAGED_AGENTS = ("assignment-coordinator", "assignment-verifier", "course-profile-curator")
MANAGED_MARKER = ".calvin-autonomy-managed"
# The tree this package was installed from.  In plugin mode it is the plugin
# root, and the skills and agents the host loads are read from here.
SOURCE_ROOT = Path(__file__).resolve().parents[2]


def _present(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def install_mode(workspace: Path) -> str:
    """``plugin`` when setup ran with ``--plugin``, else ``project``.

    Read from the marker setup writes, so doctor checks the layout that was
    actually installed rather than guessing from what happens to exist.
    """
    marker = Path(workspace) / MANAGED_MARKER
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "project"
    return "plugin" if "mode=plugin" in lines else "project"


def launcher_name() -> str:
    """The launcher this platform can execute: a .cmd on Windows, sh elsewhere."""
    return "coursework.cmd" if os.name == "nt" else "coursework"


def diagnose(project_root: Path, workspace: Path) -> dict[str, Any]:
    """Return read-only setup checks; optional OCR is reported as a warning."""
    project_root = Path(project_root).resolve()
    workspace = Path(workspace).resolve()
    blockers: list[str] = []
    warnings: list[str] = []
    mode = install_mode(workspace)

    python_ok = sys.version_info >= (3, 10)
    if not python_ok:
        blockers.append("Python 3.10 or newer is required")

    dependencies = {}
    for module, purpose in REQUIRED_MODULES.items():
        available = importlib.util.find_spec(module) is not None
        dependencies[module] = {"available": available, "purpose": purpose}
        if not available:
            blockers.append(f"required Python module is missing: {module}")

    discovery_paths = {
        "codex_skills": project_root / ".agents" / "skills" / "complete-assignment" / "SKILL.md",
        "claude_skills": project_root / ".claude" / "skills" / "complete-assignment" / "SKILL.md",
        "codex_coordinator": project_root / ".codex" / "agents" / "assignment-coordinator.toml",
        "claude_coordinator": project_root / ".claude" / "agents" / "assignment-coordinator.md",
    }
    if mode == "plugin":
        # The Claude Code plugin delivers skills and agents from the plugin
        # root; nothing is copied into the project, and the plugin does not
        # serve Codex.  Check the plugin's own copies, which is all a CLI can
        # see: whether the plugin is enabled in Claude Code is not visible here.
        discovery_paths = {
            "claude_skills": SOURCE_ROOT / "skills" / "complete-assignment" / "SKILL.md",
            "claude_coordinator": SOURCE_ROOT / ".claude" / "agents" / "assignment-coordinator.md",
        }
    discovery = {name: _present(path) for name, path in discovery_paths.items()}
    for name, available in discovery.items():
        if not available:
            blockers.append(f"project integration is missing: {name}")

    # Check every managed skill and agent, not just one of each.  Reporting
    # ready on a tree holding one skill out of six is the failure this tool
    # exists to catch.
    if mode == "plugin":
        skills = {
            name: {"claude": _present(SOURCE_ROOT / "skills" / name / "SKILL.md")}
            for name in MANAGED_SKILLS
        }
        agents = {
            name: {"claude": _present(SOURCE_ROOT / ".claude" / "agents" / f"{name}.md")}
            for name in MANAGED_AGENTS
        }
    else:
        skills = {
            name: {
                "codex": _present(project_root / ".agents" / "skills" / name / "SKILL.md"),
                "claude": _present(project_root / ".claude" / "skills" / name / "SKILL.md"),
            }
            for name in MANAGED_SKILLS
        }
        agents = {
            name: {
                "codex": _present(project_root / ".codex" / "agents" / f"{name}.toml"),
                "claude": _present(project_root / ".claude" / "agents" / f"{name}.md"),
            }
            for name in MANAGED_AGENTS
        }
    for name, hosts in skills.items():
        for host, available in hosts.items():
            if not available:
                blockers.append(f"managed skill is missing for {host}: {name}")
    for name, hosts in agents.items():
        for host, available in hosts.items():
            if not available:
                blockers.append(f"managed agent is missing for {host}: {name}")

    launcher = project_root / ".calvin-autonomy" / "bin" / launcher_name()
    launcher_ok = launcher.is_file() and not launcher.is_symlink()
    if not launcher_ok:
        blockers.append("project-local coursework launcher is missing")

    workspace_ok = workspace.is_dir() and not workspace.is_symlink()
    if not workspace_ok:
        blockers.append("private workspace is missing or unsafe")

    from .ocr import (
        HANDWRITING_LIMIT, RASTER_DPI, RASTERIZER_NAME, engine_probe, rasterizer_available,
    )
    ocr_engine = engine_probe()
    if ocr_engine is None:
        warnings.append("automatic OCR engine is unavailable; image sources remain in the review queue")
    pdf_rasterizer = rasterizer_available()
    if ocr_engine is not None and not pdf_rasterizer:
        warnings.append(
            f"PDF rasterizer {RASTERIZER_NAME} is unavailable; scanned PDF sources remain in the "
            "review queue while image sources can still be transcribed automatically"
        )

    return {
        "schema_version": 1,
        "ready": not blockers,
        "python": {
            "version": ".".join(str(value) for value in sys.version_info[:3]),
            "supported": python_ok,
        },
        "dependencies": dependencies,
        "project_discovery": discovery,
        "managed_skills": skills,
        "managed_agents": agents,
        "install_mode": mode,
        "launcher": {"available": launcher_ok, "name": launcher_name()},
        "workspace": {"available": workspace_ok},
        "ocr": {
            "automatic_engine_available": ocr_engine is not None,
            "automatic_engine": ocr_engine.name if ocr_engine is not None else None,
            "scope": "bulk scans of printed pages",
            "limits": HANDWRITING_LIMIT,
            "pdf_rasterizer_available": pdf_rasterizer,
            "pdf_raster_dpi": RASTER_DPI,
            "manual_review_supported": True,
        },
        "blockers": blockers,
        "warnings": warnings,
    }


__all__ = ["diagnose", "install_mode", "launcher_name"]
