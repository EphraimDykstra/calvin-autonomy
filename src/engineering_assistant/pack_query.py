"""Answer a question about a shipped pack without handing over the pack.

A pack used to be a document the host read before doing anything for a course,
so a student paid for every rule in it on every question, and would have paid
more each time a pack grew.  Here a pack is a store: the host asks for a card
(what this pack knows, and how well), then for the nodes it needs by address.
What comes back is bounded by the question and by ``max_bytes``, never by how
many courses are installed.

There is no index and no term search, on purpose.  Packs are read from disk on
each call, which takes about a millisecond for all of them, so there is nothing
that can drift from the packs.  And a ranker that misses a synonym would report
"no rule" for a rule that exists; the card lists every node instead, and the
host, which is better at matching meaning than a word list is, chooses from
all of them.

Every answer carries a ``status``.  Anything other than ``found`` has no
``body``, so a miss is never shaped like a rule.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .curriculum import (
    BOOK_FILE,
    BOOKS_DIR,
    COVERAGE_DIMENSIONS,
    COVERAGE_LEVELS,
    DEFAULT_CURRICULUM,
    SHARED_DIR,
    CurriculumError,
    books_for_pack,
    load_book,
    load_pack,
    load_packs,
    load_tool_pack,
    load_tool_packs,
)


# About 2,000 tokens.  Large enough for any single node shipped today, small
# enough that asking for a whole block of a rich pack is a visible decision.
DEFAULT_MAX_BYTES = 8000

GUIDE = "guide"
GUIDE_FILE = "methods.md"
EXEMPLARS = "exemplars"
TOOL_PREFIX = "tool:"
BOOK_PREFIX = "book:"

# Packs state provenance under either name; both answer "says who".
_PROVENANCE_KEYS = ("basis", "source")

# The card carries these whole, so listing them as contents would repeat them.
# A book has no coverage block: its pointer policy is its honesty statement.
_CARD_WHOLE = ("course", "book", "coverage", "pointer_policy", "addressing")
_CARD_HEAD = frozenset({"schema_version", *_CARD_WHOLE})

_DIMENSION_OF = {"assignment_families": "assignments"}

_PACK_ID = re.compile(r"[a-z0-9][a-z0-9-]*")

_NEXT = {
    "no_pack": (
        "No pack is installed for this. Say so plainly, use `pack show tool:calvin-engineering` "
        "for the conventions that hold across courses, and ask the student for a handout or a graded example."
    ),
    "no_rules_for_dimension": (
        "This pack has no rules of this kind. Say so plainly and ask the student for a handout "
        "or a graded example. Do not substitute another course's rule or a generic one."
    ),
    "no_such_address": (
        "Nothing is at this address. Choose from `contents`, which lists every node here, or from the "
        "`children` of the nearest node that does exist."
    ),
    "over_budget": "Ask for the listed children one at a time, or raise --max-bytes deliberately.",
}


def _size(value: Any) -> int:
    return len(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _children(node: Any) -> list[tuple[str, Any]]:
    """The addressable children of a node.

    A mapping's keys and a list's items that carry an ``id``.  A list without
    ids on every item has no children and is fetched whole: inventing
    positional ids would give addresses that change when an item is inserted.
    """
    if isinstance(node, dict):
        return list(node.items())
    if isinstance(node, list) and node and all(isinstance(x, dict) and isinstance(x.get("id"), str) for x in node):
        return [(item["id"], item) for item in node]
    return []


def _guide_sections(directory: Path) -> dict[str, dict[str, str]]:
    """Split a pack's prose guide on its second-level headings, keyed by slug."""
    path = directory / GUIDE_FILE
    if not path.is_file() or path.is_symlink():
        return {}
    sections: dict[str, dict[str, str]] = {}
    for part in re.split(r"(?m)^(?=## )", path.read_text(encoding="utf-8")):
        if not part.strip():
            continue
        title = part.splitlines()[0][3:].strip() if part.startswith("## ") else "preamble"
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        if slug in sections:
            # The second section would be unreachable, and a host would be
            # told the pack has less guidance than it does.
            raise CurriculumError(f"{directory.name}/{GUIDE_FILE}: two sections share the heading {title!r}")
        sections[slug] = {"title": title, "text": part}
    return sections


def _exemplar_texts(directory: Path, pack: dict[str, Any]) -> dict[str, str]:
    """The text of every exemplar beside a pack, keyed by exemplar id.

    A host is told never to open a file under the curriculum, so an exemplar
    served by no address is one no careful host can read.  A course pack's
    families name exemplars by id, and the file is ``exemplars/<id>.*``.  A
    tool pack lists each exemplar with the file that holds it.
    """
    folder = directory / EXEMPLARS
    texts: dict[str, str] = {}
    listed = pack.get(EXEMPLARS)
    if isinstance(listed, list):
        for item in listed:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            path = directory / str(item.get("file"))
            # The pack chooses this path, so it is held inside the folder.
            if path.parent != folder or path.is_symlink() or not path.is_file():
                raise CurriculumError(
                    f"{directory.name}: exemplar {item['id']!r} names {item.get('file')!r}, "
                    f"which is not a file directly under {EXEMPLARS}/"
                )
            texts[item["id"]] = path.read_text(encoding="utf-8")
        return texts
    if not folder.is_dir():
        return texts
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.is_symlink():
            continue
        if path.stem in texts:
            # One id, two files: a host asking for it would get whichever sorted first.
            raise CurriculumError(f"{directory.name}/{EXEMPLARS}: two files answer to the exemplar id {path.stem!r}")
        texts[path.stem] = path.read_text(encoding="utf-8")
    return texts


def _load(ref: str, root: Path) -> dict[str, Any] | None:
    """Return the pack ``ref`` names, or None.  A malformed pack still raises."""
    if not isinstance(ref, str):
        return None
    ref = ref.lower()
    if ref.startswith(TOOL_PREFIX):
        name, directory, file_name, loader = ref[len(TOOL_PREFIX):], Path(root) / SHARED_DIR, "pack.json", load_tool_pack
    elif ref.startswith(BOOK_PREFIX):
        name, directory, file_name, loader = ref[len(BOOK_PREFIX):], Path(root) / SHARED_DIR / BOOKS_DIR, BOOK_FILE, load_book
    else:
        name, directory, file_name, loader = ref, Path(root), "pack.json", load_pack
    # The pattern is what keeps a reference inside the curriculum directory.
    if not _PACK_ID.fullmatch(name):
        return None
    path = directory / name / file_name
    if not path.is_file() or path.is_symlink():
        return None
    pack = loader(path)
    return {
        "ref": ref,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "pack": pack,
        "guide": _guide_sections(path.parent),
        "exemplars": _exemplar_texts(path.parent, pack),
    }


def _contents(entry: dict[str, Any]) -> dict[str, Any]:
    """Every node in the pack, by name only.  This is what makes a miss recoverable."""
    contents: dict[str, Any] = {}
    for key, value in entry["pack"].items():
        if key in _CARD_HEAD or value is None:
            continue
        if isinstance(value, dict):
            contents[key] = list(value)
        elif _children(value):
            contents[key] = [{k: item[k] for k in ("id", "title", "when") if k in item} for item in value]
        else:
            contents[key] = {"bytes": _size(value)}
    if entry["guide"]:
        contents[GUIDE] = [
            {"id": slug, "title": section["title"], "bytes": len(section["text"].encode("utf-8"))}
            for slug, section in entry["guide"].items()
        ]
    # A tool pack lists its exemplars itself, above; a course pack's are files.
    if entry["exemplars"] and EXEMPLARS not in entry["pack"]:
        contents[EXEMPLARS] = [
            {"id": exemplar_id, "bytes": len(text.encode("utf-8"))}
            for exemplar_id, text in entry["exemplars"].items()
        ]
    return contents


def _coverage_level(pack: dict[str, Any], head: str) -> str | None:
    level = (pack.get("coverage") or {}).get(_DIMENSION_OF.get(head, head))
    return level if level in COVERAGE_LEVELS else None


def _resolve(entry: dict[str, Any], address: str) -> tuple[bool, Any, Any]:
    """Walk ``address`` from the pack root.  Returns (found, node, parent)."""
    segments = address.split(".")
    if segments[0] == GUIDE:
        if len(segments) == 1:
            return bool(entry["guide"]), {slug: s["text"] for slug, s in entry["guide"].items()}, None
        section = entry["guide"].get(segments[1]) if len(segments) == 2 else None
        return section is not None, section and section["text"], None
    if segments[0] == EXEMPLARS and EXEMPLARS not in entry["pack"]:
        if len(segments) == 1:
            return bool(entry["exemplars"]), dict(entry["exemplars"]), None
        text = entry["exemplars"].get(segments[1]) if len(segments) == 2 else None
        return text is not None, text, None
    node: Any = entry["pack"]
    parent: Any = None
    for segment in segments:
        match = [child for name, child in _children(node) if name == segment]
        if not match:
            return False, None, None
        parent, node = node, match[0]
    # A key stated as null is found: packs leave a value null on purpose where
    # it varies by assignment, and "no such address" would deny the key exists.
    return True, node, parent


def _nearest(entry: dict[str, Any], address: str) -> tuple[list[str], Any]:
    """The deepest node on the way to ``address`` that does exist, and the way to it."""
    node: Any = entry["pack"]
    reached: list[str] = []
    for segment in address.split("."):
        match = [child for name, child in _children(node) if name == segment]
        if not match:
            break
        node = match[0]
        reached.append(segment)
    return reached, node


def _miss(entry: dict[str, Any], address: str) -> dict[str, Any]:
    """A miss, with what sits beside it when the host got most of the way there.

    Near the top, the whole store's contents is the useful list, and the answer
    carries it.  Deep inside a store it is not: a host that found the right
    chapter and asked for a table it does not hold needs that chapter's tables,
    not the list of chapters again.
    """
    miss: dict[str, Any] = {"address": address, "status": "no_such_address"}
    reached, near = _nearest(entry, address)
    if len(reached) >= 2:
        prefix = ".".join(reached)
        miss["resolved_to"] = prefix
        miss["children"] = [
            {"address": f"{prefix}.{name}", "title": child["title"]}
            if isinstance(child, dict) and isinstance(child.get("title"), str)
            else {"address": f"{prefix}.{name}"}
            for name, child in _children(near)
        ]
    return miss


def _basis(node: Any, parent: Any, name: str) -> Any:
    if isinstance(node, dict):
        for key in _PROVENANCE_KEYS:
            if key in node:
                return node[key]
    # Some blocks keep their provenance beside them: rendering, rendering_basis.
    if isinstance(parent, dict) and f"{name}_basis" in parent:
        return parent[f"{name}_basis"]
    return None


def _over_budget(result: dict[str, Any]) -> dict[str, Any]:
    """Replace a found node's body with the names and sizes of its children."""
    prefix = result["address"] + "."
    children = [{"address": prefix + name, "bytes": _size(child)} for name, child in _children(result["body"])]
    return {"address": result["address"], "status": "over_budget", "bytes": result["bytes"], "children": children}


def _result(entry: dict[str, Any], address: str) -> dict[str, Any]:
    pack = entry["pack"]
    head = address.split(".")[0]
    level = _coverage_level(pack, head)
    found, node, parent = _resolve(entry, address)
    if not found or (node is None and level == "none"):
        if level == "none":
            return {"address": address, "status": "no_rules_for_dimension", "coverage": level}
        return _miss(entry, address)

    result = {"address": address, "status": "found", "coverage": level, "bytes": _size(node)}
    name = address.split(".")[-1]
    if node is None:
        # Found, and null: the pack names this key and declines to give it a
        # value.  Left bare, a host reads null as missing data or as "no limit".
        result["null_note"] = (
            "the pack states this key and leaves it null on purpose; null is neither a default nor "
            "a rule, so take the value from the student's own assignment or ask"
        )
        if isinstance(parent, dict) and isinstance(parent.get(f"{name}_note"), str):
            result["pack_note"] = parent[f"{name}_note"]
    basis = _basis(node, parent, name)
    result["basis"] = basis
    if basis is None:
        # The honest answer to "says who" is then that the pack does not say.
        # The coverage note is never re-read as a basis for one rule.
        if head == GUIDE:
            result["basis_note"] = "guide prose; the basis is on the rule nodes it describes"
        elif head == EXEMPLARS:
            result["basis_note"] = "an exemplar illustrates a shape and is not a rule; the rules it follows carry the basis"
        elif any(_basis(child, None, "") is not None for _, child in _children(node)):
            result["basis_note"] = "this node states no basis of its own; each child below carries its own"
        else:
            about = f"; {_DIMENSION_OF.get(head, head)} coverage is {level}" if level else ""
            result["basis_note"] = f"this pack states no basis for this node{about}"
    result["body"] = node
    if head == EXEMPLARS and isinstance(node, dict) and node.get("id") in entry["exemplars"]:
        # A tool pack's entry says what the exemplar shows; the file is the
        # exemplar.  The host pays for the text, so the budget counts it.
        result["text"] = entry["exemplars"][node["id"]]
        result["bytes"] += len(result["text"].encode("utf-8"))
    return result


def _no_pack(ref: Any) -> dict[str, Any]:
    return {"status": "no_pack", "ref": ref, "next": _NEXT["no_pack"]}


def show(ref: str, root: Path = DEFAULT_CURRICULUM) -> dict[str, Any]:
    """The card: what this pack covers and how well, and the name of every node."""
    entry = _load(ref, root)
    if entry is None:
        return _no_pack(ref)
    pack = entry["pack"]
    card: dict[str, Any] = {"status": "found", "pack": entry["ref"], "sha256": entry["sha256"]}
    if isinstance(pack.get("pack"), dict):
        card["title"] = pack["pack"].get("title")
    # Whole, notes included: the note says which part is thin, and that is the
    # half a student most needs to hear.
    card.update({key: pack[key] for key in _CARD_WHOLE if key in pack})
    if "course" in pack:
        # The edge is stored once, on the book.  A course pack never names a
        # book, so the two cannot disagree; nothing of the book is copied here.
        books = books_for_pack(entry["ref"], root)
        if books:
            card["books"] = [BOOK_PREFIX + book_id for book_id in books]
    if isinstance(pack.get("course_policy"), dict):
        card["policy_confidence"] = pack["course_policy"].get("confidence")
    fmt = pack.get("format")
    if isinstance(fmt, dict) and "pipeline_support" in fmt:
        card["pipeline"] = fmt["pipeline_support"]
    card["contents"] = _contents(entry)
    card["next"] = "Fetch nodes with `pack get <ref> <block>.<name>`, for example format.figures or methods.<id>."
    return card


def get(
    ref: str,
    addresses: list[str],
    root: Path = DEFAULT_CURRICULUM,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Exact nodes by address, each with its basis, within ``max_bytes`` for the call."""
    if not addresses:
        raise ValueError("name at least one address")
    entry = _load(ref, root)
    if entry is None:
        return _no_pack(ref)

    results = [_result(entry, address) for address in addresses]
    out = _answer(entry, results)
    # The budget bounds the response, because that is what the host pays for;
    # counting only the rule bodies let the envelope push a call over.  The
    # last addresses give way first, since the caller listed the first ones
    # first.  A response with no body left cannot shrink further: it is the
    # list of what the pack holds, which is what makes a miss recoverable.
    while _size(out) > max_bytes:
        found = [i for i, r in enumerate(results) if r["status"] == "found"]
        if not found:
            break
        results[found[-1]] = _over_budget(results[found[-1]])
        out = _answer(entry, results)
    if _size(out) > max_bytes:
        # A deep miss lists its neighbours with titles, which help a host
        # choose.  The addresses are what it cannot do without, so when the
        # listing is what breaks the budget the titles go and they stay.
        for result in results:
            if "resolved_to" in result:
                result["children"] = [{"address": child["address"]} for child in result["children"]]
        out = _answer(entry, results)
    return out


def _answer(entry: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [r["status"] for r in results if r["status"] != "found"]
    out: dict[str, Any] = {
        "status": failed[0] if failed else "found",
        # Read the count: "found" with fewer nodes than were asked for would
        # otherwise pass for a complete answer.
        "found": f"{len(results) - len(failed)} of {len(results)}",
        "pack": entry["ref"],
        "sha256": entry["sha256"],
        "results": results,
    }
    if failed:
        out["next"] = _NEXT[failed[0]]
        # What this store admits it does not hold.  For a book that is what its
        # index leaves out, which is how a host tells "not indexed" from "not
        # in the book".
        pack = entry["pack"]
        out["coverage_notes"] = (pack.get("coverage") or {}).get("notes") or (pack.get("book") or {}).get("index_coverage")
        # An over-budget node lists its own children, and so does a miss deep
        # in a store.  Any other miss needs the whole store's contents, so the
        # host chooses from everything there is.
        if any(r["status"] != "over_budget" and "resolved_to" not in r for r in results if r["status"] != "found"):
            out["contents"] = _contents(entry)
    return out


def find(text: str, root: Path = DEFAULT_CURRICULUM) -> dict[str, Any]:
    """Resolve what a student called a course to the pack ids that could be meant.

    Every match is returned, because one course number can have a lab pack and
    a lecture pack that give different answers.
    """
    def squash(value: Any) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

    query = squash(text)
    if not query:
        raise ValueError("name a course code, title or pack id")
    matches = []
    for pack_id, pack in load_packs(root).items():
        course = pack.get("course") if isinstance(pack.get("course"), dict) else {}
        if not any(query in squash(field) for field in (pack_id, course.get("code"), course.get("title"))):
            continue
        fmt = pack.get("format")
        match = {
            "pack": pack_id,
            "code": course.get("code"),
            "title": course.get("title"),
            "coverage": {d: pack["coverage"][d] for d in COVERAGE_DIMENSIONS},
        }
        if isinstance(fmt, dict) and isinstance(fmt.get("deliverable"), str):
            match["deliverable"] = fmt["deliverable"]
        matches.append(match)
    if not matches:
        return {"status": "no_pack", "query": text, "next": _NEXT["no_pack"]}
    out: dict[str, Any] = {"status": "found", "matches": matches}
    if len(matches) > 1:
        out["next"] = "More than one pack matches. Match the pack to the deliverable, not to the course number."
    return out


def list_packs(root: Path = DEFAULT_CURRICULUM) -> dict[str, Any]:
    """One short line per pack, for the one question that needs them all."""
    packs = [
        {
            "pack": pack_id,
            "code": (pack.get("course") or {}).get("code"),
            "format/methods/assignments": "/".join(pack["coverage"][d] for d in COVERAGE_DIMENSIONS),
        }
        for pack_id, pack in load_packs(root).items()
    ]
    return {
        "status": "found",
        "count": len(packs),
        "packs": packs,
        "tools": [TOOL_PREFIX + tool_id for tool_id in load_tool_packs(root)],
    }


def exit_code(out: dict[str, Any]) -> int:
    """Zero when the store answered truthfully, including "I have nothing for that".

    A host that sees a failing exit tends to conclude the tool is broken and
    open the pack files itself, which is the reading this module exists to
    replace.  Only a wrong address is the caller's mistake.
    """
    statuses = {out.get("status")} | {r.get("status") for r in out.get("results", [])}
    return 1 if "no_such_address" in statuses else 0


__all__ = ["DEFAULT_MAX_BYTES", "exit_code", "find", "get", "list_packs", "show"]
