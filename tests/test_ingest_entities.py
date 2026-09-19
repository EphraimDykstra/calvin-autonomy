"""Entity expansion in DOCX and XLSX parts is refused by declaration (#39).

These tests check this project's own refusal reason, never an exception type
or the interpreter's behaviour.  Python 3.14's expat refuses a billion-laughs
document on its own.  The 3.10 and 3.12 runners that gate merges may not, and
most workbook parts go to lxml instead of expat.  So each hostile fixture
here must fail on the declaration alone.  The trivial-entity fixtures expand
to a few characters, and every interpreter and parser accepts them before
this change.  That is what makes them evidence.
"""

import tempfile
import unittest
import zipfile
from pathlib import Path

from engineering_assistant.ingest import _DocumentTypeScan, extract_source_blocks, ingest

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
SPREADSHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
DOCUMENT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

REFUSED = "declares a document type definition"
UNCHECKABLE = "could not be checked for a document type definition"

TRIVIAL_DTD = '<!DOCTYPE w:document [<!ENTITY a "xx"><!ENTITY b "&a;&a;">]>'


def _laughs_dtd(root):
    entities = ['<!ENTITY l0 "lol">']
    for level in range(1, 11):
        entities.append(f'<!ENTITY l{level} "' + f"&l{level - 1};" * 10 + '">')
    return f"<!DOCTYPE {root} [" + "".join(entities) + "]>"


def _document_xml(text, dtd=""):
    return (
        f'<?xml version="1.0"?>{dtd}'
        f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'
    )


def _workbook_members(shared_string="cell", **overrides):
    """A complete workbook openpyxl will open, so its parts really get parsed."""
    members = {
        "[Content_Types].xml": '<?xml version="1.0"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>",
        "_rels/.rels": '<?xml version="1.0"?>'
        f'<Relationships xmlns="{PACKAGE}">'
        f'<Relationship Id="rId1" Type="{DOCUMENT}/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>",
        "xl/workbook.xml": '<?xml version="1.0"?>'
        f'<workbook xmlns="{SPREADSHEET}" xmlns:r="{DOCUMENT}">'
        '<sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0"?>'
        f'<Relationships xmlns="{PACKAGE}">'
        f'<Relationship Id="rId1" Type="{DOCUMENT}/worksheet" Target="worksheets/sheet1.xml"/>'
        f'<Relationship Id="rId2" Type="{DOCUMENT}/sharedStrings" Target="sharedStrings.xml"/>'
        "</Relationships>",
        "xl/worksheets/sheet1.xml": '<?xml version="1.0"?>'
        f'<worksheet xmlns="{SPREADSHEET}"><sheetData>'
        '<row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>',
        "xl/sharedStrings.xml": '<?xml version="1.0"?>'
        f'<sst xmlns="{SPREADSHEET}" count="1" uniqueCount="1"><si><t>{shared_string}</t></si></sst>',
    }
    members.update(overrides)
    return members


def _with_dtd(xml, dtd):
    """Insert a DTD straight after the XML declaration."""
    declaration = '<?xml version="1.0"?>'
    assert xml.startswith(declaration)
    return declaration + dtd + xml[len(declaration):]


class EntityDeclarationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "sources"
        self.source.mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    def _archive(self, name, members):
        """Built at test time so no hostile binary is committed."""
        path = self.source / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for member, data in members.items():
                archive.writestr(member, data)
        return path

    def assertRefused(self, result, member, reason=REFUSED):
        self.assertEqual(result["status"], "error", result)
        self.assertEqual(result["blocks"], [])
        self.assertIn(reason, result["reason"])
        self.assertIn(repr(member), result["reason"])

    # -- DOCX --------------------------------------------------------------

    def test_docx_trivial_entity_is_refused_by_declaration_not_by_size(self):
        """Expands to four characters, so no amplification limit anywhere is involved."""
        path = self._archive("trivial.docx", {"word/document.xml": _document_xml("&b;", TRIVIAL_DTD)})

        self.assertRefused(extract_source_blocks(path), "word/document.xml")

    def test_docx_billion_laughs_is_refused_with_this_projects_reason(self):
        path = self._archive("laughs.docx", {"word/document.xml": _document_xml("&l10;", _laughs_dtd("w:document"))})

        self.assertRefused(extract_source_blocks(path), "word/document.xml")

    def test_docx_doctype_without_internal_subset_is_refused(self):
        dtd = '<!DOCTYPE w:document SYSTEM "http://example.invalid/w.dtd">'
        path = self._archive("external.docx", {"word/document.xml": _document_xml("text", dtd)})

        self.assertRefused(extract_source_blocks(path), "word/document.xml")

    def test_docx_dtd_in_utf16_is_refused(self):
        """A byte search for <!DOCTYPE would miss this; the part parser would not."""
        xml = _document_xml("&b;", TRIVIAL_DTD).replace('version="1.0"?>', 'version="1.0" encoding="UTF-16"?>', 1)
        path = self._archive("utf16.docx", {"word/document.xml": xml.encode("utf-16")})

        self.assertRefused(extract_source_blocks(path), "word/document.xml")

    def test_docx_part_expat_cannot_read_is_refused_not_passed(self):
        """UCS-4 is forbidden by OOXML, and the DTD inside cannot be checked."""
        xml = _document_xml("&b;", TRIVIAL_DTD).encode("utf-32-be")
        path = self._archive("ucs4.docx", {"word/document.xml": xml})

        self.assertRefused(extract_source_blocks(path), "word/document.xml", UNCHECKABLE)

    def test_docx_refusal_reaches_the_ingested_catalog(self):
        """ingest() extracts through the same path, so it records the refusal too."""
        self._archive("trivial.docx", {"word/document.xml": _document_xml("&b;", TRIVIAL_DTD)})

        catalog = ingest(self.source, self.root / "workspace", "demo")

        (document,) = catalog["documents"]
        self.assertEqual(document["status"], "error")
        self.assertEqual(document["blocks"], [])
        self.assertIn(REFUSED, document["error"])

    # -- XLSX --------------------------------------------------------------

    def test_xlsx_dtd_in_shared_strings_is_refused(self):
        """openpyxl parses the strings table with stdlib expat."""
        members = _workbook_members("&b;")
        members["xl/sharedStrings.xml"] = _with_dtd(members["xl/sharedStrings.xml"], TRIVIAL_DTD.replace("w:document", "sst"))
        path = self._archive("strings.xlsx", members)

        self.assertRefused(extract_source_blocks(path), "xl/sharedStrings.xml")

    def test_xlsx_dtd_in_workbook_part_is_refused(self):
        """openpyxl parses workbook.xml with lxml, a different parser from the strings table."""
        members = _workbook_members()
        members["xl/workbook.xml"] = _with_dtd(members["xl/workbook.xml"], TRIVIAL_DTD.replace("w:document", "workbook"))
        path = self._archive("workbook.xlsx", members)

        self.assertRefused(extract_source_blocks(path), "xl/workbook.xml")

    def test_xlsx_part_in_an_encoding_expat_cannot_read_is_refused(self):
        """lxml reads UTF-32, which expat cannot, so an unchecked part must not pass.

        Before this change, this workbook opened and the entity expanded into
        the sheet title as "xxxx".
        """
        members = _workbook_members()
        workbook = members["xl/workbook.xml"].replace('<sheet name="S"', '<sheet name="&b;"')
        members["xl/workbook.xml"] = _with_dtd(workbook, TRIVIAL_DTD.replace("w:document", "workbook")).encode("utf-32")
        path = self._archive("ucs4.xlsx", members)

        self.assertRefused(extract_source_blocks(path), "xl/workbook.xml", UNCHECKABLE)

    def test_xlsx_dtd_in_any_member_is_refused(self):
        """Relationships choose which parts get parsed, so every member is checked."""
        members = _workbook_members()
        members["xl/custom/part.bin"] = '<?xml version="1.0"?>' + TRIVIAL_DTD.replace("w:document", "x") + "<x>&b;</x>"
        path = self._archive("anymember.xlsm", members)

        self.assertRefused(extract_source_blocks(path), "xl/custom/part.bin")

    def test_xlsx_billion_laughs_is_refused_with_this_projects_reason(self):
        members = _workbook_members("&l10;")
        members["xl/sharedStrings.xml"] = _with_dtd(members["xl/sharedStrings.xml"], _laughs_dtd("sst"))
        path = self._archive("laughs.xlsx", members)

        self.assertRefused(extract_source_blocks(path), "xl/sharedStrings.xml")

    # -- Survivors ---------------------------------------------------------

    def test_entity_free_docx_still_extracts_predefined_and_character_references(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            "<!-- prolog comment --><?mso-application progid=\"Word.Document\"?>"
            f'<w:document xmlns:w="{W}"><w:body>'
            "<w:p><w:r><w:t>q &lt; 7 &amp; T &gt; 300 &quot;K&quot; &apos;x&apos;</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>&#916;p &#x2248; 2.5 kPa µ</w:t></w:r></w:p>"
            "</w:body></w:document>"
        )
        path = self._archive("legit.docx", {"word/document.xml": xml})

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "extracted", result)
        self.assertEqual(
            [block["text"] for block in result["blocks"]],
            ["q < 7 & T > 300 \"K\" 'x'", "Δp ≈ 2.5 kPa µ"],
        )

    def test_entity_free_utf16_docx_still_extracts(self):
        xml = _document_xml("&#916;T &amp; µ").replace('version="1.0"?>', 'version="1.0" encoding="UTF-16"?>', 1)
        path = self._archive("utf16-legit.docx", {"word/document.xml": xml.encode("utf-16")})

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "extracted", result)
        self.assertEqual([block["text"] for block in result["blocks"]], ["ΔT & µ"])

    def test_entity_free_xlsx_with_binary_members_still_extracts(self):
        """Non-XML parts such as images and VBA projects are not mistaken for XML."""
        members = _workbook_members("A &amp; B &#x3A9;")
        members["xl/media/image1.png"] = b"\x89PNG\r\n\x1a\n" + bytes(range(256))
        members["xl/vbaProject.bin"] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(range(256))
        members["xl/printerSettings/printerSettings1.bin"] = b""
        members["xl/printerSettings/printerSettings2.bin"] = b"\x00\x00\x00\x00" + bytes(range(256))
        members["docProps/thumbnail.ico"] = b"\x00\x00\x01\x00" + bytes(range(256))
        path = self._archive("legit.xlsm", members)

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "extracted", result)
        self.assertEqual([block["text"] for block in result["blocks"]], ["A & B Ω"])

    # -- Scanner -----------------------------------------------------------

    def test_declaration_split_across_every_chunk_boundary_is_still_refused(self):
        data = _document_xml("&b;", TRIVIAL_DTD).encode()
        scan = _DocumentTypeScan("word/document.xml")
        with self.assertRaisesRegex(ValueError, REFUSED):
            for index in range(len(data)):
                scan.feed(data[index : index + 1])
            scan.feed(b"", final=True)


if __name__ == "__main__":
    unittest.main()
