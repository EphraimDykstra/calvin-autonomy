#!/usr/bin/env python3
"""Build curriculum/_shared/textbooks/<book-id>/book.json from extracted pointer data.

This is a one-shot authoring aid, not part of the runtime, and not re-runnable
on a clean machine: it reads the raw reconciliation output under /tmp, which is
transient. It is committed as a provenance record of how the shipped pointer
files were derived, so a reviewer can see the rules rather than infer them from
the output.

What a book.json is, and is not
-------------------------------
It is a POINTER index: which text a course uses, which chapter covers which
topic, and which appendix table holds which property, by number and title. It
is never the table. No value from any table body appears here, and none may be
added. A number in this file is only ever a table label, a printed page number,
an edition, a substance name, or a condition quoted from a table's own printed
title.

Provenance is recorded per item, never asserted in bulk
-------------------------------------------------------
`basis` is derived from evidence, not stamped uniformly. An appendix entry
claims two-source confirmation only when its label was found BOTH in the
front-matter contents listing AND as a caption in the book's own body. The rest
say plainly that they rest on the contents listing alone. Overstating this is
the same failure the project exists to prevent, and the uniform-basis version of
this script committed it.

Ids are addresses, and the A-9 lesson is built into them
--------------------------------------------------------
There is no alias layer: the on-disk key is what a session types. So a table id
and a figure id are deliberately not confusable - `table-a-9` and `figure-a-9`
are different addresses. Across these courses "A-9" is a saturated-water table
in one Cengel text, an air-properties table in another, and a T-s DIAGRAM in a
third; asking a book for `table-a-9` when its A-9 is a figure must miss rather
than quietly return a chart.

Authorship is omitted for any text written by a Calvin instructor: this
repository forbids instructor names in tracked files with no exception for
bibliography, and a title plus edition is enough to find the book.
"""
from __future__ import annotations

import json
from pathlib import Path

SRC = Path("/tmp/tbx")
OUT = Path(__file__).resolve().parents[1] / "curriculum" / "_shared" / "textbooks"

BASIS_BOTH = "contents listing and a caption in the book body, reconciled"
BASIS_TOC = "contents listing only (-layout and -raw reconciled); no body caption confirmed"
BASIS_CH_BOTH = "contents listing, reconciled across -layout and -raw extractions"
# In-chapter tables and figures are not listed in the front matter, so unlike
# the appendix entries they rest on ONE source: the caption printed above the
# item itself. Said plainly rather than borrowing the appendix two-source claim.
BASIS_CAPTION = "caption printed in the book body (single source; chapter items are not listed in the front matter)"

# Books whose author is or may be a Calvin instructor are cited by title and
# edition only. The repository's name scan does not exempt bibliography.
AUTHOR_WITHHELD = {"statistics-physical-sciences-engineering"}

# Extracted book_id -> shipped id. Two passes reached the Cengel fluids book
# under different ids (chapter map and table index were built separately); both
# map to one slug so the book ships once, not twice.
RENAME = {
    "cengel-boles-thermo-8e": "cengel-boles-thermodynamics-8e",
    "cengel-ghajar-hmt-5e": "cengel-ghajar-heat-mass-transfer-5e",
    "cengel-cimbala-fluids-4e": "cengel-cimbala-fluid-mechanics-4e",
    "fluid209": "cengel-cimbala-fluid-mechanics-4e",
    "chem209": "felder-rousseau-bullard-chemical-processes-4e",
    "engr204": "zekavat-electrical-engineering-1e",
    "stat241": "statistics-physical-sciences-engineering",
    "engr305-mechanics": "riley-sturges-morris-mechanics-of-materials-6e",
    "dorf-bishop-mcs-13e": "dorf-bishop-modern-control-systems-13e",
    "322a-navedtra": "basic-machines-navpers-10624a",
    "322b-macaulay": "macaulay-new-way-things-work-1998",
    "giancoli_phys_4ed": "giancoli-physics-scientists-engineers-4e",
}

CITATION = {
    "statistics-physical-sciences-engineering":
        "Statistics for the Physical Sciences and Engineering (January 2021 printing)",
}

# Course ids as an extraction recorded them -> the installed pack's course id.
# `stat241` was a straight typo: the pack is `stats241`, so the edge pointed at
# nothing and the book would never have appeared on its course's card.
COURSE_FIX = {"stat241": "stats241"}

# What a host cannot otherwise know: whether a label it failed to find is absent
# from the BOOK or merely absent from this INDEX. Only the record can say, and a
# book that says nothing reads as complete. So every book carries this, and a
# section that was never surveyed says so rather than being left out - "nobody
# looked" is a different claim from "there is none". Values are prose for a host
# to display; nothing here is machine-read.
INDEX_COVERAGE = {
    "cengel-ghajar-heat-mass-transfer-5e": {
        "chapters": "complete: all 17 chapters, including the three web chapters",
        "appendix": "complete: all 20 SI appendix items (A-1..A-20) indexed",
        "chapter_tables": "complete: all 70 in-chapter tables indexed",
        "chapter_figures": (
            "PARTIAL: 303 of 440 indexed. 137 captions could not be cleanly extracted from "
            "this two-column scan and were dropped rather than guessed at; several were "
            "pulling property values out of adjacent worked examples, which this index must "
            "never carry. A figure absent from this record may still exist in the book."
        ),
        "titles": (
            "102 of the 373 in-chapter entries carry title_partial. A caption ends at a "
            "period; one that never reached its period may have adjacent body text in its "
            "tail, so the title is shown but should not be trusted as the book's exact "
            "wording. The pointer itself - the label and the printed page - is unaffected."
        ),
        "english_units": (
            "NOT indexed. Appendix 2 repeats the SI tables in English units as A-1E..A-17E, "
            "printed pp. 935-958. Labels are not recorded here."
        ),
        "note": (
            "Chapters 15-17 are web chapters with no printed page numbers and are not in the "
            "main PDF; their tables and figures are not indexed."
        ),
    },
    "cengel-boles-thermodynamics-8e": {
        "appendix": "complete: all 34 SI appendix items (A-1..A-34), tables and figures alike",
        "chapters": (
            "NOT indexed. This book has no chapter list in this record at all, so a chapter "
            "or a chapter-numbered table such as 'Table 3-1' cannot be resolved here. Only "
            "its appendix is indexed."
        ),
        "chapter_tables": "NOT indexed; see chapters above",
        "english_units": (
            "NOT indexed. Appendix 2 repeats the SI tables in English units as A-1E..A-31E, "
            "printed pp. 947-987. Note A-15E does not exist: that appendix runs A-14E to A-16E."
        ),
    },
    "cengel-cimbala-fluid-mechanics-4e": {
        "chapters": "complete: all 15 chapters",
        "appendix": "complete: all 16 SI appendix items (A-1..A-16), tables and figures alike",
        "chapter_tables": (
            "NOT indexed. In-chapter tables and figures were indexed only for the heat and "
            "mass transfer book, because only that course pair asked for them."
        ),
        "english_units": (
            "NOT indexed. Appendix 2 repeats the SI tables in English units as A-1E..A-16E, "
            "printed pp. 965-977."
        ),
    },
    "dorf-bishop-modern-control-systems-13e": {
        "chapters": "complete: all 13 chapters",
        "appendix": (
            "NOT indexed, but the appendices EXIST and are in this PDF. The publisher "
            "designates Appendices A-I as web resources; this file bundles them. Verified "
            "present: A MATLAB Basics, C Symbols/Units/Conversion Factors, D Laplace "
            "Transform Pairs, F Decibel Conversion, G Complex Numbers, H z-Transform Pairs, "
            "I Discrete-Time Evaluation. D and H are the ones a control-systems student is "
            "usually sent to. Their individual entries are not indexed here."
        ),
        "note": (
            "Appendix pages use letter-prefixed numbering (D-1, H-1), NOT the body's "
            "continuous numbering, so an appendix must never be cited by a body page number."
        ),
    },
    "felder-rousseau-bullard-chemical-processes-4e": {
        "chapters": "complete: all 10 chapters",
        "appendix": (
            "NOT indexed, but it EXISTS: Appendix B, Physical Property Tables, printed "
            "pp. 627-653. Its individual tables are not recorded here."
        ),
        "chapter_tables": "NOT indexed",
    },
    "riley-sturges-morris-mechanics-of-materials-6e": {
        "chapters": "complete: all 10 chapters",
        "appendix": (
            "NOT indexed, but it EXISTS: Appendix B, Tables of Properties, printed "
            "pp. 683-705. Its individual tables are not recorded here."
        ),
        "chapter_tables": "NOT indexed",
        "note": (
            "This PDF is a JPG scan and its text layer garbles titles, so chapter titles here "
            "are OCR-normalised reconstructions rather than verbatim transcription."
        ),
    },
    "giancoli-physics-scientists-engineers-4e": {
        "chapters": "complete: all 44 chapters, serving both Physics 133 and Physics 235",
        "appendix": (
            "NOT indexed, but they EXIST: Appendices A-F, including Mathematical Formulas, "
            "Derivatives and Integrals, Dimensional Analysis and Selected Isotopes. Their "
            "individual entries are not recorded here."
        ),
        "chapter_tables": "NOT indexed",
    },
    "zekavat-electrical-engineering-1e": {
        "chapters": "complete: all 15 chapters",
        "appendix": (
            "NOT indexed, but they EXIST: Appendix A Solving Linear Equations (p. 671), "
            "Appendix B Laplace Transform (p. 673), Appendix C Complex Numbers (p. 677). "
            "Appendix B is the one a circuits student is usually sent to. Their contents are "
            "not recorded here."
        ),
        "chapter_tables": "NOT indexed",
    },
    "statistics-physical-sciences-engineering": {
        "chapters": "complete: all 11 chapters (numbered 0-10)",
        "appendix": (
            "THERE IS NONE, and this is a finding rather than a gap. This book carries no "
            "statistical tables at all: no t, z, chi-square or F table. It is built around R "
            "throughout. A student must not be sent here to 'look up the t table', because "
            "the table does not exist in this text - not merely in this index."
        ),
        "chapter_tables": "NOT indexed",
    },
    "basic-machines-navpers-10624a": {
        "chapters": "complete: all 15 chapters",
        "appendix": "THERE IS NONE: this book's contents listing shows no appendix",
        "chapter_tables": "NOT indexed",
    },
    "macaulay-new-way-things-work-1998": {
        "structure": (
            "complete: all 39 parts and sections. This is an illustrated reference organised "
            "in named parts, not a problem-set textbook with numbered chapters."
        ),
        "appendix": "THERE IS NONE: the book ends with an index (p. 396) and carries no appendix",
        "chapter_tables": "NOT indexed; this book has no numbered tables to cite",
    },
}

THERMO = "cengel-boles-thermodynamics-8e"
HMT = "cengel-ghajar-heat-mass-transfer-5e"
FLUIDS = "cengel-cimbala-fluid-mechanics-4e"

# The collision that motivates this whole index, cross-referenced in every
# direction so a session landing on any one of them is warned about the others.
COLLISIONS = {
    (THERMO, "figure-a-9"): (
        "LABEL COLLISION. 'A-9' means three different things across the Cengel texts these "
        "courses use. HERE it is a FIGURE (T-s diagram for water) - not a lookup table. In "
        f"{HMT} (same courses) table-a-9 is Properties of saturated water. In {FLUIDS} "
        "(ENGR 209) table-a-9 is Properties of Air at 1 atm. For saturated water BY "
        "TEMPERATURE in this book, use table-a-4."
    ),
    (HMT, "table-a-9"): (
        "LABEL COLLISION. 'A-9' means three different things across the Cengel texts these "
        "courses use. HERE it is Properties of saturated water. In "
        f"{THERMO} - the OTHER book for these same two courses - A-9 is a FIGURE (T-s "
        f"diagram) and saturated water by temperature is table-a-4. In {FLUIDS} (ENGR 209) "
        "table-a-9 is Properties of Air at 1 atm, and saturated water is table-a-3."
    ),
    (FLUIDS, "table-a-9"): (
        "LABEL COLLISION. 'A-9' means three different things across the Cengel texts these "
        "courses use. HERE it is Properties of Air at 1 atm. In "
        f"{HMT} table-a-9 is Properties of saturated water. In {THERMO} A-9 is a FIGURE "
        "(T-s diagram). Saturated water in THIS book is table-a-3."
    ),
    (FLUIDS, "table-a-3"): (
        f"Same title, different number: Properties of Saturated Water is A-3 here but A-9 in "
        f"{HMT}. Never carry a table number between books."
    ),
    # The same quantity appears twice in this book, once as an algebraic
    # expression in a table and once as a chart in a figure. A course solving
    # in EES uses the EXPRESSION; a student reading by eye uses the chart.
    # Pointing at either alone sends half the readers to the wrong object, so
    # each names the other and says which is which.
    (HMT, "table-13-1"): (
        "SAME QUANTITY, TWO FORMS. This table carries the closed-form view-factor "
        "EXPRESSIONS, including the row for coaxial parallel disks. The same "
        "relationship is also plotted as a chart at figure-13-7. If the work is being "
        "solved in a solver such as EES, this table is the right object: a chart cannot "
        "be typed into an equation solver. Confirmed against the book: this table's rows "
        "are aligned parallel rectangles, coaxial parallel disks, and perpendicular "
        "rectangles with a common edge."
    ),
    (HMT, "figure-13-7"): (
        "SAME QUANTITY, TWO FORMS. This is the CHART of the view factor between two "
        "coaxial parallel disks, for reading by eye. The identical relationship is "
        "available as a closed-form expression in the coaxial-parallel-disks row of "
        "table-13-1, which is what a solver-based method uses. Do not send a student "
        "here for a value their method computes algebraically."
    ),
    (HMT, "figure-a-20"): (
        f"The Moody chart is A-20 here but figure-a-12 in {FLUIDS}. A FIGURE in both."
    ),
    (FLUIDS, "figure-a-12"): (
        f"The Moody chart is A-12 here but figure-a-20 in {HMT}. A FIGURE in both."
    ),
}


def load(name: str) -> list[dict]:
    path = SRC / name
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()] if path.is_file() else []


def slug(book_id: str) -> str:
    return RENAME.get(book_id, book_id)


def body_confirmed() -> dict[str, list[str]]:
    path = SRC / "body_confirmed.json"
    if not path.is_file():
        raise SystemExit(
            "missing /tmp/tbx/body_confirmed.json - run verify_basis.py first. "
            "Without it every appendix entry would claim a verification it does not have."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def collect() -> dict[str, dict]:
    confirmed = body_confirmed()
    books: dict[str, dict] = {}

    for fname in sorted(p.name for p in SRC.glob("*.jsonl")):
        for row in load(fname):
            bid = slug(row["book_id"])
            entry = books.setdefault(bid, {"id": bid, "chapters": [], "tables": []})

            if row.get("record") == "book":
                incoming = {COURSE_FIX.get(c, c) for c in (row.get("course_ids") or [])}
                entry["courses"] = sorted(set(entry.get("courses", [])) | incoming)
                if row.get("citation"):
                    entry["citation"] = row["citation"]
                for key in ("pages_total", "unit_system", "printed_pages",
                            "structure", "title_fidelity"):
                    if row.get(key) is not None:
                        entry[key] = row[key]
                # The list of appendix items is the top-level `appendix` key, so
                # the prose description of the appendix cannot also be called
                # that: one word meaning two things is the confusion this index
                # exists to remove.
                if row.get("appendix") is not None:
                    entry["appendix_title"] = row["appendix"]
                note = row.get("appendix_note") or row.get("tables_note")
                if note:
                    entry["appendix_note"] = note
                if row.get("note"):
                    entry["note"] = row["note"]
                continue

            kind = row.get("kind")
            if kind in ("table", "figure"):
                label = row["label"].lower()
                item_id = f"{'table' if kind == 'table' else 'figure'}-{label}"
                is_chapter = label[0].isdigit()
                in_body = label in confirmed.get(row["book_id"], [])
                item = {
                    "id": item_id,
                    "title": row["title"],
                    "kind": kind,
                    "label": row["label"],
                    "page": row.get("page"),
                    "basis": BASIS_CAPTION if is_chapter else (BASIS_BOTH if in_body else BASIS_TOC),
                }
                if is_chapter:
                    # Kept only to group the item under its chapter; dropped
                    # from the output, because once nested the position states
                    # it and one fact should have one home.
                    item["_chapter"] = row.get("chapter")
                for key in ("gives", "indexed_by", "header_verified", "note",
                            "caption_recovered", "title_partial", "title_note"):
                    if row.get(key):
                        item[key] = row[key]
                if kind == "figure" and "note" not in item:
                    item["note"] = "A FIGURE, not a table. Never cite it for a numeric lookup."
                collision = COLLISIONS.get((bid, item_id)) or row.get("collision_note")
                if collision:
                    item["collision_note"] = collision
                entry["tables"].append(item)
            else:
                number = str(row.get("number", "")).strip()
                prefix = "part" if kind == "part" else "ch"
                # Addresses split on ".", so a dot inside an id makes the item
                # unreachable and silent: `chapters.ch-1.1` would parse as
                # chapters -> ch-1 -> 1 and miss. The printed form survives in
                # `number`, the way a table's printed label survives in `label`.
                slug_number = number.replace(".", "-")
                item = {
                    "id": f"{prefix}-{slug_number}" if number else f"{prefix}-{len(entry['chapters']) + 1}",
                    "title": row["title"],
                    "page": row.get("page"),
                    # Workers recorded per-row whether an entry survived both
                    # extractions; that value is carried, never overridden.
                    "basis": BASIS_CH_BOTH if row.get("verified") == "both" else
                             f"contents listing; verification status: {row.get('verified', 'unrecorded')}",
                }
                if number:
                    item["number"] = number
                if row.get("topics"):
                    item["topics"] = row["topics"]
                if kind == "part":
                    item["kind"] = "part"
                entry["chapters"].append(item)
    return books


def write(books: dict[str, dict]) -> list[Path]:
    written = []
    for bid, entry in sorted(books.items()):
        doc = {
            "schema_version": 1,
            "book": {
                "id": bid,
                "citation": CITATION.get(bid, entry.get("citation", "")),
                "pages_total": entry.get("pages_total"),
                "courses": entry.get("courses", []),
            },
            "pointer_policy": (
                "Pointers only. This file names which chapter or which appendix table to open. "
                "It never carries a value from a table body, and none may be added. "
                "Checks that the lookup was well formed. It cannot tell whether the value you "
                "read is correct."
            ),
            "addressing": (
                "Ids are literal addresses, reached as appendix.<item-id> and chapters.<item-id>. "
                "A table and a figure sharing a number get different ids (appendix.table-a-9 vs "
                "appendix.figure-a-9) so a request for a table can never silently return a chart. "
                "The list is called `appendix` rather than `tables` because it also holds figures "
                "and, in some books, lettered appendices that are not tables at all. "
                "Table numbers are NOT portable between books."
            ),
        }
        if bid in AUTHOR_WITHHELD:
            doc["book"]["author_withheld"] = (
                "Cited by title and edition only. This repository forbids Calvin instructor "
                "names in tracked files, with no exception for bibliography."
            )
        coverage = INDEX_COVERAGE.get(bid)
        if not coverage:
            raise SystemExit(
                f"{bid}: no index_coverage. Every book must state, section by section, what "
                f"this index covers and what it leaves out; absent reads as complete."
            )
        doc["book"]["index_coverage"] = coverage
        for key in ("appendix_title", "unit_system", "printed_pages", "appendix_note",
                    "structure", "title_fidelity", "note"):
            if entry.get(key):
                doc["book"][key] = entry[key]
        if entry["chapters"]:
            doc["chapters"] = entry["chapters"]
        if entry["tables"]:
            doc["appendix"] = entry["tables"]

        target = OUT / bid
        target.mkdir(parents=True, exist_ok=True)
        path = target / "book.json"
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


def installed_courses() -> set[str]:
    # OUT is curriculum/_shared/textbooks, so parents[1] is curriculum itself.
    return {p.parent.name for p in OUT.parents[1].glob("*/pack.json")
            if p.parent.name != "_shared"}



def nest(books: dict[str, dict]) -> None:
    """Move chapter tables and figures inside their chapter.

    A flat list of 398 items defeats the point of a queried store: listing it to
    find one table costs a caller thousands of tokens, so cost would scale with
    the book instead of with the question. Nested, a host reads the book card
    (chapters + appendix), then one chapter, then one item - three small reads.
    Addresses become chapters.ch-13.items.table-13-1.
    """
    for bid, entry in books.items():
        chapter_items = [i for i in entry["tables"] if "_chapter" in i]
        if not chapter_items:
            continue
        entry["tables"] = [i for i in entry["tables"] if "_chapter" not in i]
        by_chapter: dict[str, list] = {}
        for item in chapter_items:
            by_chapter.setdefault(item.pop("_chapter"), []).append(item)
        index = {c.get("number"): c for c in entry["chapters"]}
        orphaned = []
        for number, items in sorted(by_chapter.items(), key=lambda kv: int(kv[0])):
            chapter = index.get(number)
            if chapter is None:
                orphaned.append(number)
                continue
            chapter["items"] = sorted(items, key=lambda i: (i["kind"], int(i["label"].split("-")[1])))
        if orphaned:
            raise SystemExit(
                f"{bid}: tables/figures reference chapters {orphaned} that have no chapter "
                f"entry, so they would be unreachable. Index the chapter list first."
            )


def check(books: dict[str, dict]) -> None:
    """Fail the build rather than emit an address that cannot be reached.

    Each rule here exists because the failure it catches is SILENT: a bad id or
    a dangling course edge produces a file that parses, validates structurally
    and simply never returns the item.
    """
    packs = installed_courses()
    for bid, entry in sorted(books.items()):
        # A course edge that matches no pack means the book never appears on
        # its course's card, and nothing says so.  A book serves a course
        # NUMBER, so `engr315` legitimately attaches to the `engr315-lab` pack.
        for course in entry.get("courses", []):
            if course not in packs and not any(p.startswith(course + "-") for p in packs):
                raise SystemExit(
                    f"{bid}: course {course!r} matches no installed pack and would attach to "
                    f"nothing. Installed: {sorted(packs)}"
                )
        lists = [(key, entry[key]) for key in ("chapters", "tables")]
        lists += [(f"chapters.{c['id']}.items", c["items"])
                  for c in entry["chapters"] if c.get("items")]
        for key, items in lists:
            # A listing a host must read to find one item has to stay small, or
            # cost scales with the book instead of the question. 100 is the
            # retrieval layer's threshold for splitting a chapter's items.
            if len(items) > 100:
                raise SystemExit(
                    f"{bid}: list {key} holds {len(items)} items; over 100 a listing costs a "
                    f"host more than the lookup is worth. Split it before shipping."
                )
            ids = [it["id"] for it in items]
            dupes = {i for i in ids if ids.count(i) > 1}
            if dupes:
                raise SystemExit(f"{bid}: duplicate {key} ids would be ambiguous addresses: {sorted(dupes)}")
            for it in items:
                # Addresses split on "."; an id containing one is unreachable.
                if "." in it["id"]:
                    raise SystemExit(
                        f"{bid}: id {it['id']!r} contains '.', which makes the address "
                        f"{key}.{it['id']} unreachable. Use '-' in ids; keep the printed form "
                        f"in `number` or `label`."
                    )
                # The 8000-byte budget is a LEAF limit. A chapter that holds
                # its own items is a container: asking for it returns a listing
                # of separately addressable children, which is the behaviour we
                # want, not an over-budget body. Its children are bounded by the
                # 100-item rule above and each is checked on its own below.
                if it.get("items"):
                    continue
                size = len(json.dumps(it, ensure_ascii=False).encode())
                if size >= 8000:
                    raise SystemExit(f"{bid}: item {it['id']} is {size} bytes, over the 8000-byte item budget")


def main() -> int:
    books = collect()
    if not books:
        print(f"no extracted pointer data found under {SRC}")
        return 1
    nest(books)
    check(books)
    toc_only = sum(1 for e in books.values() for t in e["tables"] if t["basis"] == BASIS_TOC)
    both = sum(1 for e in books.values() for t in e["tables"] if t["basis"] == BASIS_BOTH)
    for path in write(books):
        print(f"wrote {path.relative_to(OUT.parents[2])} ({path.stat().st_size} bytes)")
    print(f"\nappendix entries: {both} two-source, {toc_only} contents-listing only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
