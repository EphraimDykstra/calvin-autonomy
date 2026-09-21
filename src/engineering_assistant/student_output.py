"""Render a review result as the block a student actually reads.

The student never reads this process's stdout.  In Claude Code and Codex the
CLI's output is collapsed; what the student reads is the model's reply.  So
this format exists to be reproduced verbatim inside a fenced code block, and
every decision here follows from that one fact: it is short, because a long
block gets paraphrased and a paraphrase is where a hedge quietly becomes a
verdict; it is plain ASCII with no colour and no box drawing, because it has
to survive a proportional fallback font and a phone; and it is narrow, because
it has to survive a split pane.

Nothing here decides anything.  Every verdict, number and unit is read from
the result object that ``review_work`` already built and that ``--format
json`` already prints, so the two cannot disagree.  ``tests/test_student_output.py``
holds that to a stronger line than string containment: every number printed is
parsed back and compared with the value it came from, so a rounding that
changed an answer would fail rather than read nicely.

The engine's field is ``likely_causes``, and the hedge is load bearing.  A
recognisable discrepancy shape is evidence about the arithmetic, not a finding
about what the student was thinking, so the printed word stays "likely cause".
"""

from __future__ import annotations

import textwrap
from typing import Any

# Narrow enough to survive a split pane or a phone.  The width test holds
# every line in every fixture under this.
WRAP = 56

# Label column: the longest label is "likely cause" at 12 characters.
_LABEL = 12
_VALUE_COLUMN = 2 + _LABEL + 2

# What a step name may occupy on a verdict line.  The longest verdict is
# "SIZE LOOKS WRONG", and three spaces separate the two.
_NAME_WIDTH = WRAP - 3 - len("SIZE LOOKS WRONG")

# A dimensionless answer has no unit to print.  ``parse_unit`` spells it "1"
# or "dimensionless"; printing either after the number would read as a unit.
_DIMENSIONLESS = frozenset({"1", "dimensionless", ""})


def _number(value: Any) -> str:
    """Print a number without rounding it into a different answer.

    Shortest round-trip: the printed token parses back to exactly the value it
    came from.  A float that is a whole number loses its trailing ``.0``, which
    changes how it reads and not what it is.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, int):
        return str(value)
    text = repr(float(value))
    return text[:-2] if text.endswith(".0") else text


def _quantity(value: Any, unit: Any) -> str:
    text = _number(value)
    if isinstance(unit, str) and unit not in _DIMENSIONLESS:
        return f"{text} {unit}"
    return text


def _clip(text: str, width: int) -> str:
    """Shorten to `width`, marking that something was removed.

    Used only on names, never on a number: a clipped quantity would be a
    different answer, while a clipped name is still the name of the step.
    """
    if len(text) <= width:
        return text
    return text[: max(width - 3, 0)] + "..." if width > 3 else text[:width]


def _field(label: str, value: str) -> list[str]:
    """A labelled line, wrapped at the value column when the value is long.

    The value carries a unit, and a unit is whatever the caller wrote, so it is
    wrapped rather than allowed to run past the width this format promises.
    The number always lands on the first line, ahead of any wrap.
    """
    head = f"  {label:<{_LABEL}}  "
    return textwrap.wrap(
        value, width=WRAP, initial_indent=head, subsequent_indent=" " * _VALUE_COLUMN
    ) or [head.rstrip()]


def _prose(text: str) -> list[str]:
    return textwrap.wrap(str(text), width=WRAP, initial_indent="  ", subsequent_indent="  ")


def _label_for(step: dict[str, Any], index: int) -> str:
    """Name a step.  ``id`` is optional in the input, so fall back to position.

    Clipped here and nowhere else: this name is printed both on the verdict
    line and in the attention list, and clipping at the call sites would let
    one block spell the same step two different ways.
    """
    value = step.get("id")
    return _clip(str(value) if value else f"step {index}", _NAME_WIDTH)


def _headline(name: str, verdict: str) -> str:
    return f"{name}   {verdict}"


def _range_line(magnitude: dict[str, Any]) -> list[str]:
    low, high = magnitude["range"]
    return _field("usual range", f"{_number(low)} to {_quantity(high, magnitude.get('unit'))}")


def _magnitude_note(magnitude: dict[str, Any]) -> list[str]:
    note = magnitude.get("note")
    return _prose(note) if note else []


def _course_pack_lines(note: dict[str, Any]) -> list[str]:
    """Say that the named course pack is not installed, and what is.

    The wording says what was unavailable rather than what "did not run": with
    no pack there are no ranges to check against, and a step that named one
    would have failed on its own terms anyway.  Unindented, because it is a
    caveat about the whole review rather than about any one step.
    """
    text = (
        f'No course pack is installed as "{note.get("requested")}", '
        "so no magnitude ranges were available to check against."
    )
    near = [str(pack) for pack in note.get("did_you_mean") or []]
    if near:
        text += " Did you mean " + " or ".join(near) + "?"
    return textwrap.wrap(text, width=WRAP)


def format_step(step: dict[str, Any], index: int) -> list[str]:
    """Render one step.  Returns the block's lines, verdict first."""
    name = _label_for(step, index)

    if "error" in step:
        return [_headline(name, "COULD NOT CHECK"), *_prose(step["error"])]

    magnitude = step.get("magnitude")
    implausible = isinstance(magnitude, dict) and magnitude.get("plausible") is False

    if step.get("correct"):
        # A correct step earns one line and no padded praise.  The exception is
        # a magnitude the pack calls implausible: the arithmetic being right
        # says nothing about whether the inputs were sensible, and that is the
        # honest case this tool exists for.
        if not implausible:
            value = _quantity(step.get("claimed"), step.get("unit"))
            line = f"{_headline(name, 'OK')}   {value}"
            # A long unit would push the one-liner past the width, so it falls
            # back to the labelled form, which wraps predictably.  Short cases
            # are untouched, which is what keeps the published blocks stable.
            if len(line) <= WRAP:
                return [line]
            return [_headline(name, "OK"), *_field("you wrote", value)]
        return [
            _headline(name, "SIZE LOOKS WRONG"),
            *_field("you wrote", _quantity(step.get("claimed"), step.get("unit"))),
            *_range_line(magnitude),
            # The framing comes before the pack's note, which can run long: the
            # student needs to know the arithmetic passed before reading why
            # the number is still suspect.
            *_prose("The arithmetic is right, so check the inputs."),
            *_magnitude_note(magnitude),
        ]

    lines = [
        _headline(name, "NOT RIGHT"),
        *_field("you wrote", _quantity(step.get("claimed"), step.get("unit"))),
    ]
    # A dimension mismatch is reported before anything is recomputed, so there
    # is no recomputed value to show.  Printing a line for one would invent it.
    #
    # The label is "recomputed", not "actual" or "should be".  Both of those
    # assert that the course method and the givens were right; this one says
    # what the number is -- the value rebuilt from the problem's givens -- and
    # so tells a student where to look when a given was misread from a photo.
    if "actual" in step:
        lines.extend(_field("recomputed", _quantity(step["actual"], step.get("unit"))))

    causes = step.get("likely_causes") or []
    if causes:
        for cause in causes:
            lines.extend(_field("likely cause", str(cause.get("cause", ""))))
            if cause.get("hint"):
                lines.extend(_prose(cause["hint"]))
    else:
        # Never invent a slip shape that did not match.
        lines.extend(_prose("No known slip shape matches this one."))

    if implausible:
        lines.extend(_range_line(magnitude))
        lines.extend(_magnitude_note(magnitude))
    return lines


def format_review(result: dict[str, Any]) -> str:
    """Render a whole review: a summary when there is more than one step."""
    steps = result.get("steps") or []
    blocks: list[list[str]] = []
    for index, step in enumerate(steps, start=1):
        if step.get("correct") and not (
            isinstance(step.get("magnitude"), dict) and step["magnitude"].get("plausible") is False
        ):
            # In a multi-step review a right answer does not earn a block.
            if len(steps) > 1:
                continue
        blocks.append(format_step(step, index))

    lines: list[str] = []
    # A course id that matched no installed pack is said out loud, first,
    # before any verdict: it changes what the rest of the block was able to
    # check, and it is the whole point of the field being in the result.
    note = result.get("course_pack")
    if isinstance(note, dict) and note.get("installed") is False:
        lines.extend(_course_pack_lines(note))
    if len(steps) > 1:
        if lines:
            lines.append("")
        # Counts come from the result object, never recounted here.  `checked`
        # already excludes steps that could not be checked at all.
        checked = result.get("checked", 0)
        correct = result.get("correct", 0)
        wrong = checked - correct
        unchecked = len(steps) - checked
        # Only non-zero counts are named.  A run where every step errored would
        # otherwise read "0 right, 0 wrong", and "0 wrong" reads like a pass.
        parts = [
            text
            for count, text in (
                (correct, f"{correct} right"),
                (wrong, f"{wrong} wrong"),
                (unchecked, f"{unchecked} could not be checked"),
            )
            if count
        ]
        lines.append(f"{len(steps)} steps: " + ", ".join(parts) + ".")
        attention = [
            _label_for(step, index)
            for index, step in enumerate(steps, start=1)
            if not step.get("correct") or "error" in step
        ]
        if attention:
            lines.extend(textwrap.wrap("Needs attention: " + ", ".join(attention), width=WRAP))
    for block in blocks:
        if lines:
            lines.append("")
        lines.extend(block)
    return "\n".join(lines)


__all__ = ["WRAP", "format_review", "format_step"]
