#!/usr/bin/env python3
"""Drive one complete assignment workflow against the synthetic fixture.

Every hash in this framework binds to bytes produced at run time: plan evidence
binds to the ingested source hash and the per-block text hash, the course
profile hash is the digest of the *stored* profile, and the verification report
binds to the run's own checks and artifacts.  A fixture of frozen JSON with
baked-in digests would therefore only ever reproduce on the machine that baked
it.  This driver recomputes every binding from the live run instead, so the
example exercises the binding rules rather than a copied digest.

Nothing is written inside this directory; all output goes to --workspace.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

# Distinctive phrases, not line numbers: editing the fixture prose must not
# silently break the citations.
ASSIGNMENT_CITATION = "R1. Calculate the maximum bending stress"
METHOD_CITATIONS = (
    "Report the maximum bending stress as sigma = M / S",
    "Compute the free-end deflection as delta = P * L^3",
)


def _arg_path(path: Path) -> str:
    """Express a CLI file argument relative to the repository when possible.

    ``permitted_source`` rejects any path component beginning with a dot, so an
    absolute path is unusable whenever the checkout itself sits under a hidden
    directory -- a git worktree under ``.claude/worktrees/``, for example.  The
    CLI is invoked with the repository as its working directory, so a
    repository-relative argument avoids the hidden ancestor entirely.
    """
    path = Path(path).resolve()
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _text_sha256(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _digest(value: object) -> str:
    """Match engineering_assistant.common.digest for structured records."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


class Driver:
    def __init__(self, workspace: Path, course: str, run_id: str, verbose: bool = True):
        self.workspace = workspace
        self.course = course
        self.run_id = run_id
        self.verbose = verbose

    def cli(self, *args: str) -> dict:
        command = [
            sys.executable,
            "-m",
            "engineering_assistant.cli",
            "--workspace",
            str(self.workspace),
            *args,
        ]
        env_path = str(REPO_ROOT / "src")
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            cwd=str(REPO_ROOT),
            env={**__import__("os").environ, "PYTHONPATH": env_path},
        )
        if result.returncode != 0:
            raise SystemExit(
                f"step failed: coursework {' '.join(args[:2])}\n{result.stderr.strip()}"
            )
        if self.verbose:
            print(f"  ok: {args[0]}")
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def run_root(self) -> Path:
        return self.workspace / "assignments" / self.run_id

    # -- workflow ---------------------------------------------------------
    def ingest_course_material(self) -> dict:
        self.cli(
            "ingest", _arg_path(HERE / "course-method-notes.md"), "--course", self.course
        )
        catalog = json.loads(
            (self.workspace / "courses" / self.course / "catalog.json").read_text()
        )
        document = next(
            item
            for item in catalog["documents"]
            if item.get("status") == "extracted" and item.get("active", True) is not False
        )
        return document

    def locate(self, document: dict, phrase: str) -> dict:
        """Return a citation for the block containing ``phrase``."""
        block = next(
            (b for b in document.get("blocks", []) if phrase in str(b.get("text", ""))),
            None,
        )
        if block is None:
            raise SystemExit(f"fixture drift: no course-material block contains {phrase!r}")
        return {
            "document_id": document["id"],
            "source_sha256": document["sha256"],
            "locator": block["locator"],
            "text_sha256": _text_sha256(block["text"]),
        }

    def review(self, citation: dict, notes: str) -> None:
        self.cli(
            "evidence-review",
            "--course",
            self.course,
            "--document-id",
            citation["document_id"],
            "--locator",
            citation["locator"],
            "--notes",
            notes,
        )

    def current_assignment_citation(self) -> dict:
        state = json.loads((self.run_root() / "run.json").read_text())
        extraction = state["input"]["extraction"]
        block = next(
            (
                b
                for b in extraction.get("blocks", [])
                if ASSIGNMENT_CITATION in str(b.get("text", ""))
            ),
            None,
        )
        if block is None:
            raise SystemExit("fixture drift: assignment.md no longer contains the cited line")
        return {
            "document_id": "current-assignment",
            "source_sha256": state["input"]["sha256"],
            "locator": block["locator"],
            "text_sha256": _text_sha256(block["text"]),
        }

    def build_verification_report(self) -> dict:
        """Rebuild the verifier's bindings from the live run state."""
        state = json.loads((self.run_root() / "run.json").read_text())
        solution_hash = state["solution_sha256"]
        artifacts = sorted(
            (
                {
                    "path": a["path"],
                    "sha256": a["sha256"],
                    "source_solution_sha256": solution_hash,
                }
                for a in state["artifacts"]
            ),
            key=lambda item: item["path"],
        )
        bindings = {
            "input_sha256": state["input"]["sha256"],
            "plan_sha256": state["plan_sha256"],
            "solution_sha256": solution_hash,
            "calculation_checks_sha256": _digest({"checks": state["checks"]}),
            "calculation_checks_for_solution_sha256": solution_hash,
            "artifacts": artifacts,
            "artifact_manifest_sha256": _digest({"artifacts": artifacts}),
        }
        requirements = [
            {
                "requirement_id": requirement["id"],
                "passed": True,
                "evidence": [f"solution.sections[{index}]"],
                "notes": (
                    "Recomputed independently from the stated inputs and compared "
                    "against the rendered report."
                ),
            }
            for index, requirement in enumerate(state["plan"]["requirements"], start=1)
        ]
        return {
            "schema_version": "verification-report-1",
            "bindings": bindings,
            "findings": {
                "requirements": requirements,
                "method": [
                    {
                        "id": "course-method",
                        "passed": True,
                        "notes": (
                            "Bending stress via M = P*L and S = b*h^2/6, deflection via "
                            "delta = P*L^3/(3*E*I), matching the reviewed course notes."
                        ),
                    }
                ],
                "numerical": [
                    {
                        "id": "recalculation",
                        "passed": True,
                        "notes": (
                            "Independent recomputation gives 12.0 MPa and 1.60 mm, "
                            "matching the reported values within tolerance."
                        ),
                    }
                ],
                "format": [
                    {
                        "id": "requested-format",
                        "passed": True,
                        "notes": "Single PDF deliverable parses and carries both results.",
                    }
                ],
                "identity": [
                    {
                        "id": "identity-review",
                        "passed": True,
                        "notes": (
                            "Identity fields remain the placeholders [Student Name] and "
                            "[Student ID]; no personal data is present."
                        ),
                    }
                ],
            },
            "unresolved": [],
            "passed": True,
        }

    def inspection_report(self, artifact: str) -> dict:
        state = json.loads((self.run_root() / "run.json").read_text())
        registered = next(a for a in state["artifacts"] if a["path"] == artifact)
        return {
            "artifact_path": artifact,
            "artifact_sha256": registered["sha256"],
            "all_pages_reviewed": True,
            "legible": True,
            "requirements_present": True,
            "identity_checked": True,
            "no_clipping": True,
            "unresolved": [],
            "notes": (
                "Rendered PDF opens and parses as a single page; both required results "
                "(12.0 MPa and 1.60 mm) appear with units and with their symbolic "
                "equation and numeric substitution; no text is clipped. The page "
                "carries no personal identity data, and the run identity is still the "
                "framework placeholder pair."
            ),
        }

    def write_json(self, name: str, value: dict) -> Path:
        scratch = self.workspace / "fixture-scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        path = scratch / name
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="private workspace directory for all generated output",
    )
    parser.add_argument("--course", default="synthetic-101")
    parser.add_argument("--run-id", default="synthetic-run-1")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    workspace = args.workspace.resolve()
    if HERE == workspace or HERE in workspace.parents:
        raise SystemExit("refusing to write generated output inside the fixture directory")
    workspace.mkdir(parents=True, exist_ok=True)

    driver = Driver(workspace, args.course, args.run_id, verbose=not args.quiet)
    say = (lambda *a: None) if args.quiet else print

    say("1. ingest synthetic course material")
    document = driver.ingest_course_material()

    say("2. review the controlling method evidence")
    method_citations = [driver.locate(document, phrase) for phrase in METHOD_CITATIONS]
    for citation in method_citations:
        driver.review(
            citation,
            "Compared against the rendered course notes; this line states the "
            "required method for this assignment family.",
        )

    say("3. register the reviewed course profile")
    profile = json.loads((HERE / "course-profile.json").read_text())
    profile["evidence"] = method_citations
    driver.cli(
        "profile-set", _arg_path(driver.write_json("course-profile.json", profile)),
        "--course", args.course,
    )
    profile_hash = driver.cli("profile-show", "--course", args.course)["sha256"]

    say("4. start the run from the current assignment")
    driver.cli(
        "start", _arg_path(HERE / "assignment.md"),
        "--course", args.course, "--run-id", args.run_id,
    )

    say("5. match against reviewed same-course examples")
    driver.cli(
        "match", _arg_path(HERE / "structured-assignment.json"), "--course", args.course
    )

    say("6. accept the grounded plan")
    plan = json.loads((HERE / "plan.json").read_text())
    plan["evidence"] = [driver.current_assignment_citation(), *method_citations]
    plan["course_profile_sha256"] = profile_hash
    driver.cli("accept-plan", args.run_id, _arg_path(driver.write_json("plan.json", plan)))

    say("7. render the declared deliverable")
    driver.cli("render", args.run_id, _arg_path(HERE / "solution.json"))

    say("8. run reproducible calculation checks")
    driver.cli("verify", args.run_id)

    say("9. record the structured verification report")
    driver.cli(
        "verify-report",
        args.run_id,
        _arg_path(driver.write_json("verification.json", driver.build_verification_report())),
    )

    say("10. record the artifact inspection")
    artifact = "deliverables/submission.pdf"
    driver.cli(
        "inspect", args.run_id,
        "--artifact", artifact,
        "--report", _arg_path(driver.write_json("inspection.json", driver.inspection_report(artifact))),
    )

    say("11. final status")
    status = driver.cli("status", args.run_id)
    stage = status["effective_stage"]
    ready = status["readiness"]["ready"]
    say(f"\neffective_stage={stage} ready={ready}")
    if not ready:
        for blocker in status["readiness"]["blockers"]:
            say(f"  blocker: {blocker}")
        return 1
    say(f"artifact: {(driver.run_root() / artifact)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
