"""Check a student's own finished work, step by step, and name the likely slip.

This is the check-my-work job.  The student has done the problem; the host
has read their work, from a photo or a typed answer, and writes each step as
the course's method, the inputs the student used, and the answer the student
wrote.  Each step is recomputed independently and compared.

The structure is fixed so a check cannot be built backwards.  The method is
the course's correct expression and the answer is the student's number.  A
check whose expected value came out of the expression being checked passes
every mistake it was meant to find, so this module never accepts an expected
value at all: it only accepts what the student wrote.

When a step is wrong, the discrepancy often has a recognisable shape: the
answer is the negative of the right one, or its reciprocal, or off by a power
of a thousand.  Those shapes are reported as likely causes, never as
verdicts.  The host explains the why from the course pack.
"""

from __future__ import annotations

import math
from typing import Any

from .calculations import _evaluate_dimensional
from .units import UnitError, convert, describe, expression_dimension, parse_unit, same_dimension

SCHEMA_VERSION = 1

# Students round intermediate values, so an answer within this fraction of
# the recomputed value counts as right.  A step may set its own.
DEFAULT_RELATIVE_TOLERANCE = 0.02


def _close(value: float, target: float, tolerance: float) -> bool:
    return math.isclose(value, target, rel_tol=tolerance, abs_tol=1e-12)


def classify_discrepancy(actual: float, claimed: float, dimensionless: bool, temperature: bool) -> list[dict[str, str]]:
    """Return the recognisable shapes a wrong answer has, most specific first."""
    causes: list[dict[str, str]] = []
    if actual == 0 or claimed == 0:
        return causes
    ratio = claimed / actual
    tol = 0.02
    if _close(ratio, -1.0, tol):
        causes.append({
            "cause": "sign",
            "hint": "The answer has the right size but the wrong sign. Look for a minus sign dropped or doubled, or a direction taken the wrong way.",
        })
    if dimensionless and _close(claimed * actual, 1.0, tol):
        causes.append({
            "cause": "inverted",
            "hint": "The answer is the reciprocal of the right one. A ratio is upside down: for example output over input written as input over output.",
        })
    magnitude = math.log10(abs(ratio))
    for power, what in ((3, "a thousand"), (6, "a million"), (9, "a billion")):
        if _close(abs(magnitude), power, 0.01):
            causes.append({
                "cause": "unit prefix",
                "hint": f"The answer is off by a factor of {what}. That is usually a unit prefix: g for kg, kPa for Pa, mm for m.",
            })
            break
    if _close(abs(ratio), 100.0, tol) or _close(abs(ratio), 0.01, tol):
        causes.append({
            "cause": "percent",
            "hint": "The answer is off by a factor of 100. A percentage was probably used as a fraction, or a fraction as a percentage.",
        })
    elif _close(abs(ratio), 10.0, tol) or _close(abs(ratio), 0.1, tol):
        causes.append({
            "cause": "decimal",
            "hint": "The answer is off by a factor of 10. Look for a misplaced decimal point or a dropped zero.",
        })
    if temperature and math.isclose(abs(claimed - actual), 273.15, abs_tol=0.5):
        causes.append({
            "cause": "temperature scale",
            "hint": "The answer is off by 273.15. A Celsius value was used as kelvin, or the reverse.",
        })
    return causes


def _magnitude_check(value: float, unit: str, entry: dict[str, Any]) -> dict[str, Any]:
    low, high = entry["typical_range"]
    in_range_unit = convert(value, unit, entry["unit"])
    return {
        "quantity": entry["quantity"],
        "range": [low, high],
        "unit": entry["unit"],
        "value_in_range_unit": in_range_unit,
        "plausible": low <= in_range_unit <= high,
        "note": entry.get("note"),
    }


def review_step(step: dict[str, Any], magnitudes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Recompute one step and compare it with what the student wrote."""
    result: dict[str, Any] = {"id": step.get("id"), "correct": False}
    try:
        if "expected" in step:
            raise ValueError(
                "a review step takes the student's answer, not an expected value; "
                "an expected value computed from the method would make the check a tautology"
            )
        answer = step.get("student_answer")
        if not isinstance(answer, dict) or "value" not in answer or "unit" not in answer:
            raise ValueError("student_answer needs the value and unit the student wrote")
        claimed = answer["value"]
        if isinstance(claimed, bool) or not isinstance(claimed, (int, float)) or not math.isfinite(claimed):
            raise ValueError("student_answer value must be a finite number")
        inputs = step.get("inputs")
        if not isinstance(inputs, dict) or not all(isinstance(v, dict) for v in inputs.values()):
            raise ValueError("every input needs a value and a unit, so the check converts them itself")
        tolerance = step.get("tolerance", DEFAULT_RELATIVE_TOLERANCE)
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not 0 <= tolerance < 1:
            raise ValueError("tolerance is a fraction between 0 and 1")

        # Compare dimensions before evaluating.  A mismatch is a finding about
        # the student's answer, not a failure of the check, and an inverted
        # ratio shows up here first.  Anything else that goes wrong is an
        # error in the step as written, and must not be dressed up as a hint.
        dims = {name: parse_unit(spec["unit"]).dimension for name, spec in inputs.items()}
        found = expression_dimension(step["method"], dims)
        claimed_dim = parse_unit(answer["unit"]).dimension
        if not same_dimension(found, claimed_dim):
            if same_dimension(tuple(-d for d in found), claimed_dim):
                finding = {
                    "cause": "inverted",
                    "hint": (
                        f"The answer's units are the inverse of this quantity's "
                        f"({describe(claimed_dim)} against {describe(found)}). A ratio is upside down."
                    ),
                }
            else:
                finding = {
                    "cause": "dimension",
                    "hint": (
                        f"The answer is in {answer['unit']} ({describe(claimed_dim)}), but this "
                        f"quantity has dimension {describe(found)}."
                    ),
                }
            result.update(claimed=claimed, unit=answer["unit"], likely_causes=[finding])
            return result

        actual = _evaluate_dimensional({"expression": step["method"], "unit": answer["unit"]}, inputs)
        declared = parse_unit(answer["unit"])
        result.update(
            actual=actual,
            claimed=claimed,
            unit=answer["unit"],
            tolerance=tolerance,
            correct=_close(claimed, actual, tolerance),
        )
        if not result["correct"]:
            dimensionless = same_dimension(declared.dimension, (0.0,) * 6)
            temperature = same_dimension(declared.dimension, parse_unit("K").dimension)
            result["likely_causes"] = classify_discrepancy(actual, claimed, dimensionless, temperature)

        wanted = step.get("magnitude")
        if wanted is not None:
            entry = next((m for m in magnitudes or [] if m.get("quantity") == wanted), None)
            if entry is None:
                raise ValueError(f"no magnitude in the course pack is named {wanted!r}")
            # Judge the student's own number: a correct recomputation says
            # nothing about whether the inputs they started from were sensible.
            result["magnitude"] = _magnitude_check(claimed, answer["unit"], entry)
    except (ValueError, KeyError, TypeError, UnitError, SyntaxError, ZeroDivisionError, OverflowError) as exc:
        result["error"] = str(exc)
    return result


def review_work(steps: list[dict[str, Any]], magnitudes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Review every step and summarise, without judging the student."""
    if not isinstance(steps, list) or not steps:
        raise ValueError("review needs at least one step")
    results = [review_step(step, magnitudes) for step in steps]
    return {
        "schema_version": SCHEMA_VERSION,
        "steps": results,
        "checked": sum(1 for r in results if "error" not in r),
        "correct": sum(1 for r in results if r.get("correct")),
        "needs_attention": [r["id"] for r in results if not r.get("correct") or "error" in r],
    }


__all__ = ["classify_discrepancy", "review_step", "review_work"]
