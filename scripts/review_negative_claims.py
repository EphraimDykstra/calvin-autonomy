"""Narrow a pack's prose to the few sentences where it may deny a document it relies on.

WHAT THIS IS
    A reading aid, not a gate. It reduces several thousand lines of pack prose to
    roughly ten sentences a human should read, and a human decides every one.

WHY IT EXISTS
    A pack once said, in one pitfall line, that a prompt "was not in the archived
    folder" while the same pack cited that prompt as a basis in seven other places
    and called it its primary source of rules. A pack that denies a document it
    relies on is wrong on its face, and catching it needs no filesystem access:
    the contradiction is visible from inside the repo.

WHAT A RESULT MEANS
    A clean run proves nothing. A hit proves nothing either.

    Measured against the packs as they stood when this was written: it caught the
    real case it was built for, and every one of the ten hits it produced on the
    live packs was benign. Typical benign shapes:
      - the denial governs a different noun in the same sentence
        ("no rubric beyond the one project handout" affirms the handout)
      - same head noun, different document
        ("no homework prompt survives" in a pack that cites a design project prompt)
      - same head noun, different instance
        ("the Lab 06-08 handouts were not kept" in a pack citing the Lab 01 handout)

    That precision is not a bug to be tuned out. Deciding which noun a negation
    governs, and whether two mentions share a referent, needs parsing rather than
    proximity. This tool is deliberately NOT wired into the gates: a check whose
    every current hit is benign would either fail builds for no reason or, once
    an allowlist were added for each, mostly encode its own exceptions.

    So: run it, read the hits, judge them. Do not report a clean run as evidence
    a pack is consistent, and do not treat a hit as evidence a pack is wrong.

USAGE
    python scripts/review_negative_claims.py [path ...]     # default: curriculum/
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Fields where a pack states what it BUILT ON. `precedence` is deliberately absent:
# it is an aspirational priority order, and it often names a document precisely to
# say the pack does not have one ("the homework prompt (none survive; ask the student)").
PROVENANCE_KEY = re.compile(
    r"(?i)(^|\.)(basis|source|sources|evidence_tiers?|archive_holds|derived_from|source_lineage)(\[|\.|$)"
)

HEADS = [
    "handout", "prompt", "template", "syllabus", "manual", "spec", "specification",
    "guideline", "standard", "slide", "deck", "sheet", "memo", "rubric",
    "schedule", "checklist", "instruction", "appendix", "key", "workbook",
]
_IRREGULAR = {"syllabus": "syllabi", "appendix": "appendices"}


def _variants(head: str) -> set[str]:
    return {head, _IRREGULAR.get(head, head + "s")}


_ALL_HEADS = sorted({v for h in HEADS for v in _variants(h)}, key=len, reverse=True)
_HEAD_ALT = "|".join(_ALL_HEADS)

HEAD_RE = re.compile(r"(?i)\b(" + _HEAD_ALT + r")\b")
# "the ENGR 319 memo format spec": up to four modifier words before the head noun.
DOCPHRASE_RE = re.compile(r"(?i)\b((?:[A-Za-z0-9][\w/&-]*\s+){0,4}(" + _HEAD_ALT + r"))\b")

# The negation must govern EXISTENCE. Plain negation is not denial: "a lecture deck,
# not a spec" and "not established" are qualifications, not claims of absence.
_EXIST = (r"(?:surviv\w*|kept|retain\w*|found|exist\w*|saved|archiv\w*"
          r"|available|present|reachable|in\s+the\s+(?:archive|folder))")
DENIAL_RE = re.compile(
    r"(?ix)(\bno\b|\bnot\b|\bnever\b|\bnothing\b|n't\b)[^.]{0,30}?" + _EXIST
    + r"|\bno\s+(?:\w+\s+){0,3}(?:" + _HEAD_ALT + r")\b"
)

# A clause that denies something cannot also be a citation: a basis reading
# "No report, lab manual, or report sheet survives" does not cite a lab manual.
NEG_CLAUSE_RE = re.compile(r"(?ix)\bno\b|\bnot\b|\bnever\b|\bnothing\b|n't\b|\bwithout\b")

# A bare "the handout" names no particular document, so it cannot ground a citation.
GENERIC_MODS_RE = re.compile(
    r"(?i)^(?:(?:the|a|an|one|its|their|this|that|these|those|any|each|every|some|no|only"
    r"|both|new|old|current|first|second|final|same|other|and|or|with|from|be|copied|two"
    r"|three|beyond|into|about|per|see|use|used|following|above|below)\s*)*$"
)

# Characters allowed between the head noun and the denial trigger before we stop
# believing the denial is about that noun. Proximity is a proxy for attachment and
# is the main source of benign hits; see WHAT A RESULT MEANS.
MAX_GAP = 40


def _norm(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip().lower())
    return re.sub(r"^(the|a|an|one|its|their|this|that)\s+", "", text)


def _head_of(phrase: str) -> str | None:
    match = HEAD_RE.search(phrase)
    if not match:
        return None
    found = match.group(1).lower()
    for base in HEADS:
        if found in _variants(base):
            return base
    return found


def _walk(node, path: str, out: list[tuple[str, str]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _walk(value, f"{path}.{key}", out)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk(value, f"{path}[{index}]", out)
    elif isinstance(node, str):
        out.append((path, node))


def _clauses(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+|;|,\s+(?=which\b|so\b|and\b|but\b)", text)
    return [p.strip() for p in parts if p.strip()]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _denied_heads(sentence: str) -> set[str]:
    """Head nouns whose existence this sentence appears to deny."""
    denied: set[str] = set()
    for head_match in HEAD_RE.finditer(sentence):
        head = _head_of(head_match.group(1))
        if not head:
            continue
        for denial in DENIAL_RE.finditer(sentence):
            gap = max(head_match.start() - denial.end(), denial.start() - head_match.end())
            if gap <= MAX_GAP:
                denied.add(head)
                break
    return denied


def review(pack_path: Path) -> list[dict]:
    """Return sentences where `pack_path` may deny a document it cites as a basis."""
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    strings: list[tuple[str, str]] = []
    _walk(pack, "", strings)

    cited: dict[str, set[str]] = defaultdict(set)
    cited_at: dict[str, set[str]] = defaultdict(set)
    for path, value in strings:
        if not PROVENANCE_KEY.search(path):
            continue
        for clause in _clauses(value):
            if NEG_CLAUSE_RE.search(clause):
                continue
            for match in DOCPHRASE_RE.finditer(clause):
                phrase = match.group(1)
                modifiers = HEAD_RE.sub("", phrase).strip()
                if GENERIC_MODS_RE.match(modifiers):
                    continue
                head = _head_of(phrase)
                if head:
                    cited[head].add(_norm(phrase))
                    cited_at[head].add(path)

    # One denying sentence is one thing for a human to judge, even when it names
    # several head nouns. "the ENGR 319 memo format spec" carries both `memo` and
    # `spec`, and reporting that contradiction twice just makes the output longer.
    merged: dict[tuple[str, str], dict] = {}
    for path, value in strings:
        for sentence in _sentences(value):
            for head in _denied_heads(sentence):
                if head not in cited:
                    continue
                key = (path, sentence)
                hit = merged.get(key)
                if hit is None:
                    hit = merged[key] = {
                        "pack": pack_path.parent.name,
                        "heads": [],
                        "cited_documents": [],
                        "several_documents_share_this_head": False,
                        "cited_at": [],
                        "denied_at": path,
                        "sentence": sentence,
                    }
                hit["heads"].append(head)
                hit["cited_documents"] = sorted(set(hit["cited_documents"]) | cited[head])
                hit["cited_at"] = sorted(set(hit["cited_at"]) | cited_at[head])
                # Ambiguous only if some single head noun has several cited documents;
                # two different head nouns naming one document is not ambiguity.
                if len(cited[head]) > 1:
                    hit["several_documents_share_this_head"] = True

    hits = list(merged.values())
    for hit in hits:
        hit["heads"] = sorted(set(hit["heads"]))
        # `head` kept for readability when a sentence denies exactly one kind of thing.
        hit["head"] = hit["heads"][0] if len(hit["heads"]) == 1 else "/".join(hit["heads"])
    return hits


def main(argv: list[str]) -> int:
    roots = [Path(a) for a in argv[1:]] or [Path("curriculum")]
    packs: list[Path] = []
    for root in roots:
        packs.extend(sorted(root.rglob("pack.json")) if root.is_dir() else [root])

    hits: list[dict] = []
    for pack in packs:
        hits.extend(review(pack))

    focused = [h for h in hits if not h["several_documents_share_this_head"]]
    print(f"packs read: {len(packs)}")
    print(f"sentences to judge: {len(focused)}"
          f"  (plus {len(hits) - len(focused)} where several cited documents share the head noun)")
    print("A clean run proves nothing. A hit proves nothing. Read each one and decide.")
    print("=" * 72)
    for hit in focused:
        print(f"\n[{hit['pack']}] denies a {hit['head']!r}; the pack cites: {hit['cited_documents']}")
        print(f"  cited at : {', '.join(hit['cited_at'][:3])}")
        print(f"  denied at: {hit['denied_at']}")
        print(f"  sentence : {hit['sentence'][:300]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
