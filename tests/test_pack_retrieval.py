"""A pack is a store the host queries, never a document it reads.

Two properties are tested here because a student cannot check either one.
Cost follows the question: what comes back is bounded by what was asked for,
never by how many courses are installed.  And a miss is loud: a query that
finds nothing must not be shaped like an answer, because a host handed
something answer-shaped will format a lab report from it.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.cli import main
from engineering_assistant.curriculum import DEFAULT_CURRICULUM, SCHEMA_VERSION, CurriculumError
from engineering_assistant.pack_query import DEFAULT_MAX_BYTES, get, show


# A sentence that appears only inside a rule body, so a card that leaks rule
# bodies is caught by looking for it.
BODY_SENTINEL = "Interpolate linearly between the two bracketing rows."


def _pack(**overrides):
    pack = {
        "schema_version": SCHEMA_VERSION,
        "course": {"id": "engr000", "code": "ENGR 000", "title": "Example Course",
                   "professor": None, "terms_observed": ["Example Term"]},
        "coverage": {"format": "high", "methods": "partial", "assignments": "partial",
                     "notes": "Methods rest on one worked handout."},
        "course_policy": {"source": "none found", "confidence": "unknown", "term_observed": None,
                          "summary": "No syllabus was found, so the policy is unknown.",
                          "permitted": [], "prohibited": [],
                          "student_asked": None, "professor_answer": None},
        "format": {
            "deliverable": "technical memo",
            "figures": {"caption_position": "below", "basis": "spec"},
            "tables": {"caption_position": "above", "source": "memo spec + lab prompt"},
        },
        "methods": [
            {"id": "table-lookup", "title": "Property table lookup", "when": "A state is fixed by two properties.",
             "steps": [BODY_SENTINEL], "pitfalls": ["Reading the wrong pressure row."]},
            {"id": "energy-balance", "title": "Control volume energy balance", "when": "Steady flow device.",
             "steps": ["Write the balance before substituting."], "pitfalls": [], "basis": "worked handout"},
        ],
        "assignment_families": [
            {"id": "lab-memo", "title": "Lab memo", "stages": ["final"], "deliverables": ["memo"],
             "what_good_looks_like": ["States the result first."], "exemplars": [], "basis": "spec"},
        ],
    }
    pack.update(overrides)
    return pack


class _Store(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _install(self, pack_id, pack):
        directory = self.root / pack_id
        directory.mkdir(parents=True)
        (directory / "pack.json").write_text(json.dumps(pack), encoding="utf-8")


class CardTests(_Store):
    def test_the_card_lists_every_node_and_no_rule_body(self):
        self._install("engr000", _pack())
        card = show("engr000", root=self.root)
        self.assertEqual(card["status"], "found")
        contents = json.dumps(card["contents"])
        for address in ("figures", "tables", "table-lookup", "energy-balance", "lab-memo"):
            self.assertIn(address, contents)
        # The card is what makes a miss recoverable, so it must be complete;
        # it is also read on most questions, so it must not carry the rules.
        self.assertNotIn(BODY_SENTINEL, json.dumps(card))

    def test_the_card_carries_coverage_honesty_verbatim(self):
        self._install("engr000", _pack())
        card = show("engr000", root=self.root)
        self.assertEqual(card["coverage"]["methods"], "partial")
        self.assertEqual(card["coverage"]["notes"], "Methods rest on one worked handout.")


class GetTests(_Store):
    def test_a_node_comes_back_verbatim_with_its_basis(self):
        pack = _pack()
        self._install("engr000", pack)
        out = get("engr000", ["format.figures"], root=self.root)
        self.assertEqual(out["status"], "found")
        self.assertEqual(out["found"], "1 of 1")
        (node,) = out["results"]
        self.assertEqual(node["body"], pack["format"]["figures"])
        self.assertEqual(node["basis"], "spec")
        self.assertEqual(node["coverage"], "high")

    def test_provenance_written_as_source_is_still_the_basis(self):
        self._install("engr000", _pack())
        (node,) = get("engr000", ["format.tables"], root=self.root)["results"]
        self.assertEqual(node["basis"], "memo spec + lab prompt")

    def test_a_rule_with_no_stated_basis_says_so_and_invents_none(self):
        # Most shipped methods state no basis.  The honest answer to "says who"
        # is then "the pack does not say", not the coverage note re-read as one.
        self._install("engr000", _pack())
        (node,) = get("engr000", ["methods.table-lookup"], root=self.root)["results"]
        self.assertEqual(node["status"], "found")
        self.assertIsNone(node["basis"])
        self.assertIn("states no basis", node["basis_note"])
        self.assertIn("partial", node["basis_note"])

    def test_a_value_left_null_on_purpose_is_found_and_explained(self):
        # A page budget that varies by stage is stated as null.  Reported as a
        # missing address it would deny the key exists; reported bare, a host
        # reads it as "no limit".
        pack = _pack()
        pack["format"]["rendering"] = {
            "max_body_pages": None,
            "max_body_pages_note": "Set per stage: 3 pages for a pre-submission, 4 for a final.",
        }
        self._install("engr000", pack)
        (node,) = get("engr000", ["format.rendering.max_body_pages"], root=self.root)["results"]
        self.assertEqual(node["status"], "found")
        self.assertIsNone(node["body"])
        self.assertIn("null on purpose", node["null_note"])
        self.assertEqual(node["pack_note"], "Set per stage: 3 pages for a pre-submission, 4 for a final.")

    def test_list_items_are_addressed_by_id(self):
        pack = _pack()
        self._install("engr000", pack)
        (node,) = get("engr000", ["methods.energy-balance"], root=self.root)["results"]
        self.assertEqual(node["body"], pack["methods"][1])
        self.assertEqual(node["basis"], "worked handout")


class FailClosedTests(_Store):
    def test_a_miss_is_not_shaped_like_an_answer(self):
        self._install("engr000", _pack())
        out = get("engr000", ["format.margins"], root=self.root)
        self.assertEqual(out["status"], "no_such_address")
        self.assertEqual(out["found"], "0 of 1")
        (miss,) = out["results"]
        self.assertNotIn("body", miss)
        self.assertNotIn("basis", miss)
        # "Here is what this pack does cover": the whole list, so the host
        # chooses from everything rather than from whatever a ranker surfaced.
        self.assertIn("figures", json.dumps(out["contents"]))
        self.assertIn("table-lookup", json.dumps(out["contents"]))

    def test_no_format_coverage_is_reported_not_approximated(self):
        self._install("engr000", _pack(
            coverage={"format": "none", "methods": "partial", "assignments": "partial",
                      "notes": "No format handout survives."},
            format=None,
        ))
        out = get("engr000", ["format.figures"], root=self.root)
        self.assertEqual(out["status"], "no_rules_for_dimension")
        (miss,) = out["results"]
        self.assertNotIn("body", miss)
        self.assertEqual(miss["coverage"], "none")
        self.assertEqual(out["coverage_notes"], "No format handout survives.")

    def test_a_partial_hit_is_never_reported_as_found(self):
        self._install("engr000", _pack())
        out = get("engr000", ["format.figures", "format.margins"], root=self.root)
        self.assertNotEqual(out["status"], "found")
        self.assertEqual(out["found"], "1 of 2")

    def test_an_unknown_pack_is_named_as_unknown(self):
        self._install("engr000", _pack())
        for ref in ("engr999", "../engr000", "_shared", ""):
            with self.subTest(ref=ref):
                out = get(ref, ["format"], root=self.root)
                self.assertEqual(out["status"], "no_pack")
                self.assertNotIn("results", out)
                self.assertEqual(show(ref, root=self.root)["status"], "no_pack")


class BudgetTests(_Store):
    def test_an_over_budget_node_returns_its_children_not_its_body(self):
        self._install("engr000", _pack())
        out = get("engr000", ["methods"], root=self.root, max_bytes=120)
        self.assertEqual(out["status"], "over_budget")
        (node,) = out["results"]
        self.assertNotIn("body", node)
        children = {child["address"]: child["bytes"] for child in node["children"]}
        self.assertEqual(set(children), {"methods.table-lookup", "methods.energy-balance"})
        self.assertTrue(all(size > 0 for size in children.values()))

    def test_the_budget_bounds_the_whole_response_not_just_the_rule_bodies(self):
        # Found in a real session: two nodes whose bodies fit the budget came
        # back in a response 5% over it, because the envelope was not counted.
        # The host pays for the response, so that is what the budget means.
        # Rules the size of real ones, so a body outweighs a list of its parts.
        pack = _pack(methods=[
            {"id": f"method-{n}", "title": f"Method {n}", "when": "Always.",
             "steps": [f"Step {n}: " + "work the balance through each device in turn. " * 30], "pitfalls": []}
            for n in range(4)
        ])
        self._install("engr000", pack)
        addresses = [f"methods.method-{n}" for n in range(4)]
        whole = get("engr000", addresses, root=self.root, max_bytes=100_000)
        self.assertEqual(whole["status"], "found")
        bodies = sum(r["bytes"] for r in whole["results"])
        size = len(json.dumps(whole, separators=(",", ":")).encode("utf-8"))
        # A budget every body fits within, but the response does not.
        budget = (bodies + size) // 2
        self.assertTrue(bodies < budget < size)
        out = get("engr000", addresses, root=self.root, max_bytes=budget)
        self.assertLessEqual(len(json.dumps(out, separators=(",", ":")).encode("utf-8")), budget)
        self.assertEqual(out["status"], "over_budget")
        # Earlier addresses are the caller's priority, so the last ones give way.
        self.assertEqual(out["results"][0]["status"], "found")
        self.assertEqual(out["results"][-1]["status"], "over_budget")
        self.assertNotIn("body", out["results"][-1])

    def test_another_course_changes_nothing_about_this_one(self):
        # The scaling rule, executable: course 40 must not make course 1 cost
        # a byte more.
        self._install("engr000", _pack())
        before = (show("engr000", root=self.root), get("engr000", ["format", "methods.table-lookup"], root=self.root))
        other = _pack()
        other["course"] = {**other["course"], "id": "engr001", "code": "ENGR 001"}
        self._install("engr001", other)
        after = (show("engr000", root=self.root), get("engr000", ["format", "methods.table-lookup"], root=self.root))
        self.assertEqual(json.dumps(before, sort_keys=True), json.dumps(after, sort_keys=True))


EXEMPLAR_TEXT = "# Exemplar: lab memo shape\n\nObjective, Methods, Results. Every number here is invented.\n"


class ExemplarTests(_Store):
    """An exemplar is part of the store.

    The skill forbids opening a file under the curriculum, so an exemplar no
    address reaches is an exemplar no careful host can ever read.  That shipped
    once: packs named their exemplars and nothing could fetch them.
    """

    def _install_tool(self, tool_id, exemplars, files):
        directory = self.root / "_shared" / tool_id
        (directory / "exemplars").mkdir(parents=True)
        for name, text in files.items():
            (directory / "exemplars" / name).write_text(text, encoding="utf-8")
        (directory / "pack.json").write_text(json.dumps({
            "schema_version": SCHEMA_VERSION,
            "pack": {"id": tool_id, "kind": "tool", "title": "Example Tool"},
            "coverage": {"conventions": "high", "methods": "partial", "pitfalls": "high", "notes": "One handout."},
            "conventions": {}, "methods": [], "exemplars": exemplars,
        }), encoding="utf-8")

    def test_a_course_exemplar_is_on_the_card_and_comes_back_whole(self):
        self._install("engr000", _pack())
        folder = self.root / "engr000" / "exemplars"
        folder.mkdir()
        (folder / "lab-memo-shape.md").write_text(EXEMPLAR_TEXT, encoding="utf-8")
        card = show("engr000", root=self.root)
        self.assertEqual(card["contents"]["exemplars"], [{"id": "lab-memo-shape", "bytes": len(EXEMPLAR_TEXT.encode())}])
        (node,) = get("engr000", ["exemplars.lab-memo-shape"], root=self.root)["results"]
        self.assertEqual(node["status"], "found")
        self.assertEqual(node["body"], EXEMPLAR_TEXT)
        miss = get("engr000", ["exemplars.final-report"], root=self.root)
        self.assertEqual(miss["status"], "no_such_address")
        self.assertIn("lab-memo-shape", json.dumps(miss["contents"]))

    def test_a_pack_with_no_exemplars_offers_none(self):
        self._install("engr000", _pack())
        self.assertNotIn("exemplars", show("engr000", root=self.root)["contents"])

    def test_a_tool_exemplar_keeps_its_entry_and_gains_the_file_text(self):
        item = {"id": "loop", "file": "exemplars/loop.txt", "shows": "Gauge to absolute."}
        self._install_tool("ees0", [item], {"loop.txt": "P_abs = P_gauge + P_atm\n"})
        (node,) = get("tool:ees0", ["exemplars.loop"], root=self.root)["results"]
        self.assertEqual(node["body"], item)
        self.assertEqual(node["text"], "P_abs = P_gauge + P_atm\n")
        # The host pays for the text, so the budget has to count it.
        self.assertGreaterEqual(node["bytes"], len(node["text"]))

    def test_two_files_answering_to_one_exemplar_id_are_refused(self):
        self._install("engr000", _pack())
        folder = self.root / "engr000" / "exemplars"
        folder.mkdir()
        (folder / "shape.md").write_text("one", encoding="utf-8")
        (folder / "shape.txt").write_text("two", encoding="utf-8")
        with self.assertRaises(CurriculumError) as raised:
            show("engr000", root=self.root)
        self.assertIn("shape", str(raised.exception))


def _book(**overrides):
    book = {
        "schema_version": SCHEMA_VERSION,
        "book": {"id": "example-thermo-1e", "citation": "Example Thermodynamics, 1st ed.",
                 "pages_total": 900, "courses": ["engr000"]},
        "pointer_policy": "Pointers only. It cannot tell whether the value you read is correct.",
        "addressing": "Ids are literal addresses.",
        "appendix": [
            {"id": "table-a-9", "title": "Properties of saturated water", "kind": "table", "label": "A-9",
             "page": 920, "basis": "contents listing and a caption in the book body, reconciled"},
            {"id": "figure-a-9", "title": "T-s diagram for water", "kind": "figure", "label": "A-9",
             "page": "927-928", "basis": "contents listing only; no body caption confirmed"},
        ],
    }
    book.update(overrides)
    return book


class BookTests(_Store):
    """A textbook is shared: two courses point at one book and nothing is copied."""

    def _install_book(self, book, book_id="example-thermo-1e"):
        directory = self.root / "_shared" / "textbooks" / book_id
        directory.mkdir(parents=True)
        (directory / "book.json").write_text(json.dumps(book), encoding="utf-8")

    def setUp(self):
        super().setUp()
        self._install("engr000", _pack())

    def test_a_table_and_a_figure_sharing_a_number_are_different_addresses(self):
        self._install_book(_book())
        (table,) = get("book:example-thermo-1e", ["appendix.table-a-9"], root=self.root)["results"]
        self.assertEqual(table["body"]["kind"], "table")
        self.assertEqual(table["body"]["page"], 920)
        # The two-source and contents-only bases are different claims, and the
        # difference must reach the host word for word.
        self.assertEqual(table["basis"], "contents listing and a caption in the book body, reconciled")
        (figure,) = get("book:example-thermo-1e", ["appendix.figure-a-9"], root=self.root)["results"]
        self.assertEqual(figure["body"]["page"], "927-928")
        self.assertEqual(figure["basis"], "contents listing only; no body caption confirmed")
        # Asking for table A-10 must miss, never fall back to a near label.
        self.assertEqual(get("book:example-thermo-1e", ["appendix.table-a-10"], root=self.root)["status"], "no_such_address")
        self.assertEqual(get("book:example-thermo-1e", ["appendix.a-9"], root=self.root)["status"], "no_such_address")

    def test_the_book_card_carries_its_pointer_policy_whole(self):
        self._install_book(_book())
        card = show("book:example-thermo-1e", root=self.root)
        self.assertEqual(card["status"], "found")
        self.assertIn("cannot tell whether the value you read is correct", card["pointer_policy"])
        self.assertIn("table-a-9", json.dumps(card["contents"]))

    def test_a_course_card_lists_the_books_that_name_it_and_copies_nothing(self):
        # One course number, several packs: a book serves the number.
        self._install("engr000-lab", _pack())
        self._install("engr0001", _pack())
        self._install_book(_book())
        for pack_id in ("engr000", "engr000-lab"):
            self.assertEqual(show(pack_id, root=self.root)["books"], ["book:example-thermo-1e"], pack_id)
        self.assertNotIn("books", show("engr0001", root=self.root))
        self.assertNotIn("table-a-9", json.dumps(show("engr000", root=self.root)))

    def test_a_book_that_cannot_be_trusted_is_refused(self):
        dotted = _book()
        dotted["appendix"][0]["id"] = "table-a.9"
        unsourced = _book()
        del unsourced["appendix"][0]["basis"]
        duplicate = _book()
        duplicate["appendix"][1]["id"] = "table-a-9"
        for label, book, message in (
            ("an id with a dot is unreachable", dotted, "contains '.'"),
            ("an entry with no basis", unsourced, "basis"),
            ("two entries sharing an id", duplicate, "more than once"),
            ("a course that matches no pack", _book(book={**_book()["book"], "courses": ["engr999"]}), "engr999"),
            ("an id that is not its directory", _book(book={**_book()["book"], "id": "other"}), "directory"),
            ("no pointer policy", _book(pointer_policy=""), "pointer_policy"),
            ("an undeclared block", _book(values=[]), "unknown top-level key"),
        ):
            with self.subTest(label):
                with tempfile.TemporaryDirectory() as tmp:
                    self.root = Path(tmp)
                    self._install("engr000", _pack())
                    self._install_book(book)
                    with self.assertRaises(CurriculumError) as raised:
                        show("book:example-thermo-1e", root=self.root)
                    self.assertIn(message, str(raised.exception))


class CommandTests(_Store):
    def _run(self, *argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["pack", "--curriculum", str(self.root), *argv])
        return code, json.loads(buffer.getvalue())

    def test_a_truthful_nothing_exits_zero_and_a_wrong_address_does_not(self):
        # A host that sees a failing exit decides the tool is broken and opens
        # the pack file itself.  "I have nothing for that" is an answer.
        self._install("engr000", _pack())
        self._install("chem000", _pack(
            coverage={"format": "none", "methods": "none", "assignments": "none", "notes": "Nothing survives."},
            format=None, methods=[], assignment_families=[],
        ))
        for argv, status, code in (
            (("get", "engr000", "format.figures"), "found", 0),
            (("get", "engr999", "format"), "no_pack", 0),
            (("get", "chem000", "format.figures"), "no_rules_for_dimension", 0),
            (("get", "engr000", "methods", "--max-bytes", "120"), "over_budget", 0),
            (("get", "engr000", "format.margins"), "no_such_address", 1),
            (("find", "ENGR 999"), "no_pack", 0),
            (("show", "engr000"), "found", 0),
            (("list",), "found", 0),
        ):
            with self.subTest(argv=argv):
                got_code, out = self._run(*argv)
                self.assertEqual((out["status"], got_code), (status, code))

    def test_one_course_number_with_two_packs_returns_both(self):
        self._install("engr000", _pack())
        lab = _pack()
        lab["format"]["deliverable"] = "lab report"
        self._install("engr000-lab", lab)
        _, out = self._run("find", "ENGR 000")
        self.assertEqual([m["pack"] for m in out["matches"]], ["engr000", "engr000-lab"])
        self.assertEqual([m["deliverable"] for m in out["matches"]], ["technical memo", "lab report"])

    def test_a_broken_pack_is_refused_not_reported_absent(self):
        self._install("engr000", _pack(coverage={"format": "high"}))
        with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit) as raised:
            main(["pack", "--curriculum", str(self.root), "show", "engr000"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("coverage is missing", err.getvalue())


def _addresses(card):
    """Every address a card offers, read off its documented shape."""
    for block, listing in card["contents"].items():
        if isinstance(listing, dict):
            yield block  # no addressable children, so it is fetched whole
            continue
        for item in listing:
            yield f"{block}.{item if isinstance(item, str) else item['id']}"


class ShippedPackRoundTripTests(unittest.TestCase):
    """There is no index to drift, so the guarantee is checked directly.

    Every address a card offers must resolve to exactly what is on disk, and
    every leaf must fit the default budget, or a host following the card would
    be refused the rule it was just told exists.
    """

    def test_every_address_on_every_card_resolves_to_the_disk_subtree(self):
        shipped = [(p.parent.name, p) for p in sorted(DEFAULT_CURRICULUM.glob("*/pack.json"))
                   if not p.parent.name.startswith("_")]
        self.assertTrue(shipped, "no shipped packs found")
        # Tool packs and textbook indexes are queried the same way, so they owe
        # the same guarantee.
        shipped += [(f"tool:{p.parent.name}", p) for p in sorted(DEFAULT_CURRICULUM.glob("_shared/*/pack.json"))]
        shipped += [(f"book:{p.parent.name}", p) for p in sorted(DEFAULT_CURRICULUM.glob("_shared/textbooks/*/book.json"))]
        checked = 0
        for pack_id, pack_file in shipped:
            on_disk = json.loads(pack_file.read_text(encoding="utf-8"))
            guide = (pack_file.parent / "methods.md")
            guide_text = guide.read_text(encoding="utf-8") if guide.is_file() else ""
            card = show(pack_id)
            self.assertEqual(card["status"], "found", pack_id)
            # Nothing on disk may be missing from the card, or a rule exists
            # that no host following the card could ever reach.
            # Blocks served from a file beside the pack rather than from a key in
            # it.  The disk-side test below checks those byte for byte.
            from_files = {"guide", "exemplars"} - set(on_disk)
            self.assertEqual(
                set(card["contents"]) - from_files,
                {k for k, v in on_disk.items() if v is not None}
                - {"schema_version", "course", "book", "coverage", "pointer_policy", "addressing"},
                pack_id,
            )
            for address in _addresses(card):
                checked += 1
                with self.subTest(pack=pack_id, address=address):
                    out = get(pack_id, [address], max_bytes=DEFAULT_MAX_BYTES)
                    self.assertEqual(out["status"], "found")
                    head, _, rest = address.partition(".")
                    if head == "guide":
                        self.assertIn(out["results"][0]["body"], guide_text)
                        continue
                    if head in from_files:
                        continue
                    block = on_disk[head]
                    if not rest:
                        expected = block
                    elif isinstance(block, dict):
                        expected = block[rest]
                    else:
                        expected = next(x for x in block if isinstance(x, dict) and x.get("id") == rest)
                    self.assertEqual(out["results"][0]["body"], expected)
        # A loop over nothing passes every assertion inside it.  579 addresses
        # were checked when this was written; packs only grow, so far fewer
        # means the cards have stopped listing what is on disk.
        self.assertGreaterEqual(checked, 500)


# Files that ship under the curriculum and are deliberately served by no
# address.  Empty on purpose.  Add a path (relative to the curriculum) only
# with a comment saying why no host will ever need to read it.
UNREACHABLE_BY_DESIGN: frozenset = frozenset()


class EveryShippedFileIsReachableTests(unittest.TestCase):
    """The round trip above starts from the cards, so it cannot see a file that
    was never put on one.  This starts from the disk.

    The skill forbids a host from opening anything under the curriculum, so a
    shipped file that no address serves has silently stopped existing.  That
    happened to every exemplar.  A new kind of file added to a pack now fails
    here until it is served or deliberately listed above.
    """

    def test_every_file_under_the_curriculum_is_served_whole_or_listed(self):
        stores = [(p.parent.name, p) for p in sorted(DEFAULT_CURRICULUM.glob("*/pack.json"))
                  if not p.parent.name.startswith("_")]
        stores += [(f"tool:{p.parent.name}", p) for p in sorted(DEFAULT_CURRICULUM.glob("_shared/*/pack.json"))]
        stores += [(f"book:{p.parent.name}", p) for p in sorted(DEFAULT_CURRICULUM.glob("_shared/textbooks/*/book.json"))]
        served = set()
        for ref, store_file in stores:
            directory = store_file.parent
            served.add(store_file)  # the store itself, covered node by node by the round trip
            contents = show(ref)["contents"]

            guide = directory / "methods.md"
            if guide.is_file():
                text = "".join(
                    get(ref, [f"guide.{section['id']}"])["results"][0]["body"]
                    for section in contents.get("guide", [])
                )
                # Every byte, not just every heading: prose before the first
                # heading, or between two, is still prose a host was meant to see.
                self.assertEqual(text, guide.read_text(encoding="utf-8"), f"{ref}: guide is not served whole")
                served.add(guide)

            for item in contents.get("exemplars", []):
                node = get(ref, [f"exemplars.{item['id']}"])["results"][0]
                self.assertEqual(node["status"], "found", f"{ref} exemplars.{item['id']}")
                if isinstance(node["body"], dict):
                    path, text = directory / node["body"]["file"], node["text"]
                else:
                    (path,) = [p for p in (directory / "exemplars").iterdir() if p.stem == item["id"]]
                    text = node["body"]
                self.assertEqual(text, path.read_text(encoding="utf-8"), f"{ref}: {path.name} is not served whole")
                served.add(path)

        shipped = {p for p in DEFAULT_CURRICULUM.rglob("*") if p.is_file() and p.name != ".DS_Store"}
        listed = {DEFAULT_CURRICULUM / name for name in UNREACHABLE_BY_DESIGN}
        unreachable = sorted(str(p.relative_to(DEFAULT_CURRICULUM)) for p in shipped - served - listed)
        self.assertEqual(unreachable, [], "shipped under the curriculum, but no address serves them")
        # The same guard as the round trip: 66 files were served when this was
        # written, and a walk that found nothing would pass everything above.
        self.assertGreaterEqual(len(served), 60)


if __name__ == "__main__":
    unittest.main()
