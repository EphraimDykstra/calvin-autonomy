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
from .units import BUILTIN_CONSTANTS, DIMENSIONLESS, UnitError, convert, describe, expression_dimension, parse_unit, same_dimension, shadowed_constants

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
            # A dimensionless answer has no unit of its own, but it is usually a
            # ratio of quantities that do: a strain from a length change in mm
            # over a length in m comes out a thousand times off.
            hint = (
                f"The ratio is off by a factor of {what}. One of the quantities in it was probably "
                "used in the wrong unit, such as millimetres divided by metres."
                if dimensionless else
                f"The answer is off by a factor of {what}. That is usually a unit prefix: g for kg, kPa for Pa, mm for m."
            )
            causes.append({"cause": "unit prefix", "hint": hint})
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


def _dimension_hint(unit: str, claimed: tuple, found: tuple) -> str:
    """Say what is wrong with the answer's units the way a person would.

    This string is read by the student in both output formats, so it says
    "a plain number with no unit" rather than restating the unit and then
    naming its dimension in SI base symbols.
    """
    if same_dimension(found, DIMENSIONLESS):
        return f"The answer is written in {unit}, but this quantity is a plain number with no unit."
    if same_dimension(claimed, DIMENSIONLESS):
        return f"The answer is written as a plain number, but this quantity has units of {describe(found)}."
    return f"The answer is written in {unit}, but this quantity has units of {describe(found)}."


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

        # A step may supply its own pi, and then its value is the one used.
        # Recorded either way, because a small discrepancy explained by
        # pi = 3.14 is a thing the reader has to be able to see.
        shadows = shadowed_constants(inputs)
        if shadows:
            result["shadowed_constants"] = shadows

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
                finding = {"cause": "dimension", "hint": _dimension_hint(answer["unit"], claimed_dim, found)}
            result.update(claimed=claimed, unit=answer["unit"], likely_causes=[finding])
            return result

        actual = _evaluate_dimensional({"expression": step["method"], "unit": answer["unit"]}, inputs)
        declared = parse_unit(answer["unit"])
        result.update(
            actual=actual,
            claimed=claimed,
            unit=answer["unit"],
            tolerance=tolerance,
            # Measured against the correct value.  math.isclose measures
            # against the larger of the two, so an overestimate would get a
            # looser limit than the stated one.
            correct=abs(claimed - actual) <= tolerance * abs(actual) + 1e-12,
        )
        if shadows:
            # Say whether "correct" is load-bearing on the supplied constant.
            # A step that supplies pi = 3, which a host can do by transcribing
            # it out of the student's own work, marks an answer of 3.0 in^2
            # correct for a circle whose area is 3.1416: the check adopts the
            # student's error as a premise and then confirms it.  Recomputing
            # with the built-in answers that without inventing a threshold,
            # and it separates the case where the constant changed nothing
            # from the case where it is the only reason the step passed.
            plain = {name: spec for name, spec in inputs.items() if name not in BUILTIN_CONSTANTS}
            try:
                exact = _evaluate_dimensional({"expression": step["method"], "unit": answer["unit"]}, plain)
            except (ValueError, KeyError, TypeError, UnitError, ZeroDivisionError, OverflowError):
                result["correct_with_builtin"] = None
            else:
                result["correct_with_builtin"] = abs(claimed - exact) <= tolerance * abs(exact) + 1e-12
        if not result["correct"]:
            dimensionless = same_dimension(declared.dimension, (0.0,) * 6)
            temperature = same_dimension(declared.dimension, parse_unit("K").dimension)
            result["likely_causes"] = classify_discrepancy(actual, claimed, dimensionless, temperature)

        wanted = step.get("magnitude")
        if wanted is not None:
            entry = next((m for m in magnitudes or [] if m.get("quantity") == wanted), None)
            if entry is None:
                # Two different failures, and saying the wrong one is a false
                # claim the student reads: with no ranges loaded at all there
                # is no pack to have been missing an entry, and the block would
                # otherwise assert one exists right below a line saying it does
                # not.
                if not magnitudes:
                    raise ValueError(
                        f"no magnitude ranges are loaded, so {wanted!r} could not be checked for size"
                    )
                raise ValueError(f"no magnitude in the course pack is named {wanted!r}")
            # Judge the student's own number: a correct recomputation says
            # nothing about whether the inputs they started from were sensible.
            result["magnitude"] = _magnitude_check(claimed, answer["unit"], entry)
    except (ValueError, KeyError, TypeError, UnitError, SyntaxError, ZeroDivisionError, OverflowError) as exc:
        result["error"] = str(exc)
    return result


def review_work(
    steps: list[dict[str, Any]],
    magnitudes: list[dict[str, Any]] | None = None,
    course_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Review every step and summarise, without judging the student.

    ``course_pack`` is passed in rather than looked up here.  Resolving a
    course id means reading the installed curriculum, and this module stays a
    pure recomputation of what the student wrote; the caller that already had
    to find the pack is the one that knows whether it found it.
    """
    if not isinstance(steps, list) or not steps:
        raise ValueError("review needs at least one step")
    results = [review_step(step, magnitudes) for step in steps]
    out: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    # Ahead of the steps, because it qualifies every one of them.  Absent
    # entirely when there is nothing to say, so the common result is unchanged.
    if course_pack is not None:
        out["course_pack"] = course_pack
    out["steps"] = results
    out["checked"] = sum(1 for r in results if "error" not in r)
    out["correct"] = sum(1 for r in results if r.get("correct"))
    out["needs_attention"] = [r["id"] for r in results if not r.get("correct") or "error" in r]
    return out


__all__ = ["classify_discrepancy", "review_step", "review_work"]
