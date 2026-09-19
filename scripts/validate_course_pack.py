"""Validate the bounded private course-pack metadata without opening originals."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REQUIRED = {"course.yaml", "style-profile.yaml", "style-profile.json"}
SECRET = re.compile(r"(?:secret|token|credential|auth|\.env|\.pem|\.p8|\.key|id_)", re.I)

def validate(root: Path) -> list[str]:
    errors: list[str] = []
    if not root.is_dir():
        return ["course-pack root is missing"]
    course = root / "course.yaml"
    style = root / "style-profile.yaml"
    style_json = root / "style-profile.json"
    if not REQUIRED.issubset({p.name for p in root.iterdir()}):
        errors.append("missing required course/style artifact")
    try:
        profile = json.loads(style_json.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"style-profile.json unreadable: {exc}")
        profile = {}
    expected = ["instructor_assignment", "instructor_template", "reviewed_course_guidance", "anonymous_student_example", "unresolved_or_image_only_evidence"]
    if profile.get("precedence") != expected:
        errors.append("style precedence does not match required authority order")
    if profile.get("review_status") != "reviewed":
        errors.append("style-profile.json is not reviewed")
    if not isinstance(profile.get("rendering"), dict) or not isinstance(profile.get("evidence"), list) or not profile.get("evidence"):
        errors.append("style-profile.json lacks rendering settings or evidence provenance")
    try:
        course_text = course.read_text(encoding="utf-8")
        course_data = yaml.safe_load(course_text) or {}
    except (OSError, yaml.YAMLError) as exc:
        errors.append(f"course.yaml unreadable: {exc}")
        course_text = ""
        course_data = {}
    if "historical_syllabus_ai_content: excluded_by_owner" not in course_text:
        errors.append("course.yaml missing historical syllabus AI exclusion")

    source_ids = {
        str(source.get("id"))
        for source in course_data.get("sources", [])
        if isinstance(source, dict) and source.get("id")
    }
    for group in ("method-cards", "assignment-families"):
        for artifact in sorted((root / group).glob("*.yaml")):
            try:
                artifact_data = yaml.safe_load(artifact.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError) as exc:
                errors.append(f"{artifact.relative_to(root)} unreadable: {exc}")
                continue
            for source_id in artifact_data.get("source_artifacts", []) or []:
                if source_id not in source_ids:
                    errors.append(
                        f"unresolved source_artifact in {artifact.relative_to(root)}: {source_id}"
                    )

    for ledger in course_data.get("source_ledgers", []) or []:
        if not isinstance(ledger, dict) or not ledger.get("path"):
            errors.append("source_ledgers contains an entry without a path")
            continue
        ledger_path = root / str(ledger["path"])
        try:
            ledger_data = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"source ledger unreadable: {ledger_path.relative_to(root)}: {exc}")
            continue
        if ledger_data.get("course_id") != course_data.get("course_id"):
            errors.append(f"source ledger course_id mismatch: {ledger_path.relative_to(root)}")
        if not isinstance(ledger_data.get("sources"), list) or not ledger_data["sources"]:
            errors.append(f"source ledger lacks sources: {ledger_path.relative_to(root)}")
        if "/Users/" in json.dumps(ledger_data):
            errors.append(f"source ledger contains an absolute user path: {ledger_path.relative_to(root)}")
    for path in root.rglob("*"):
        if path.is_file() and SECRET.search(path.name):
            errors.append(f"secret-like artifact filename: {path.name}")
        if path.is_file() and path.suffix in {".yaml", ".json"}:
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"(?:path|source):\s*([^\n]+)", text):
                value = match.group(1).strip().strip('"\'')
                if value.startswith("../") or value.startswith("/"):
                    errors.append(f"non-pack-relative source locator in {path.name}: {value}")
                if value.startswith("LAB ") or value.startswith("ENGR") or value.startswith("Computer Problem/"):
                    if not (root.parent / value).exists():
                        errors.append(f"missing source locator target: {value}")
    return errors

if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("engineering-ingestion-pilot/extended/course-pack")
    errors = validate(target)
    if errors:
        print("\n".join(errors))
        raise SystemExit(1)
    print(f"course-pack validation passed: {target}")
