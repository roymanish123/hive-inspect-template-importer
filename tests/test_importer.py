import csv
import io
import zipfile
from pathlib import Path

import openpyxl
import pytest

from hive_importer.importer import ImportFailure, MAX_BYTES, parse_export
from hive_importer.rich_text import render_html

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
HEADERS = ["Section Name", "Item Name", "Comment Name", "Comment Text"]


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    csv.writer(stream).writerows(rows)
    return stream.getvalue().encode("utf-8")


def workbook_bytes(sheets):
    # Test-only workbooks exercise the actual binary upload parser.
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def flatten(parsed):
    return [c for s in parsed["sections"] for i in s["items"] for c in i["comments"]]


def test_demo_preserves_every_comment_and_exact_html():
    data = (EXAMPLES / "residential-demo.html-text.csv").read_bytes()
    parsed = parse_export(data, "sample.csv")
    source = list(csv.reader(io.StringIO(data.decode())))
    assert [c["html"] for c in flatten(parsed)] == [r[3] for r in source[1:]]
    assert [c["name"] for c in flatten(parsed)] == [r[2] for r in source[1:]]
    assert parsed["report"]["counts"]["comments"] == 34
    assert parsed["report"]["counts"]["sections"] == 8
    assert len(parsed["rows"]) == len(source) - 1


def test_independent_edge_fixture_order_metadata_and_repeated_names():
    parsed = parse_export((EXAMPLES / "edge-cases.html-text.csv").read_bytes(), "edge.csv")
    assert [s["name"] for s in parsed["sections"]] == ["Roof", "Exterior", "Roof"]
    assert [c["name"] for c in parsed["sections"][0]["items"][0]["comments"]] == ["First", "Second", "Third"]
    assert "café · 日本語" in flatten(parsed)[0]["html"]
    assert flatten(parsed)[1]["metadata"]["Custom Setting"] == "Retain this value"
    assert {"INHERITED_SECTION", "INHERITED_ITEM", "REPEATED_SECTION", "RICH_CONTENT", "METADATA_ONLY"} <= {w["code"] for w in parsed["report"]["warnings"]}


def test_xlsx_multisheet_preamble_and_unknown_sheet_are_accounted():
    rows = [["Sample preamble"], HEADERS, ["A", "One", "Title", '<p>Keep <b>bold</b> &amp; Unicode café.</p>']]
    data = workbook_bytes({"Template": rows, "Another": [HEADERS, ["B", "Two", "Other", "Other text"]], "Settings": [["Mystery", "not mapped"]]})
    parsed = parse_export(data, "different-template.xlsx")
    counts = parsed["report"]["counts"]
    assert counts["comments"] == 2 and counts["retained_rows"] == 2
    assert counts["source_rows"] == counts["mapped_rows"] + counts["retained_rows"] == 4
    assert [s["name"] for s in parsed["sections"]] == ["A", "B"]
    assert parsed["rows"][0]["values"][0] == "Sample preamble"
    assert flatten(parsed)[0]["row"] == 3


@pytest.mark.parametrize("data,filename", [(b"", "empty.csv"), (b"garbage", "bad.xlsx"), (b"garbage", "bad.xls"), (b"a,b\n1,2", "wrong.csv"), (b"anything", "bad.pdf"), (b"x"*(MAX_BYTES+1), "big.csv")], ids=["empty", "invalid-xlsx", "invalid-xls", "wrong-headers", "unsupported-extension", "over-size-limit"])
def test_invalid_files_fail_honestly(data,filename):
    with pytest.raises(ImportFailure):
        parse_export(data,filename)


@pytest.mark.parametrize("row", [["", "", "Comment", "Body"], ["Roof", "", "Comment", "Body"]])
def test_orphans_block_import(row):
    with pytest.raises(ImportFailure, match="Import blocked") as exc:
        parse_export(csv_bytes([HEADERS,row]), "bad.csv")
    assert exc.value.issues[0]["row"] == 2


def test_new_section_does_not_inherit_previous_item():
    with pytest.raises(ImportFailure):
        parse_export(csv_bytes([HEADERS,["Roof","One","A","Text"],["Other","","B","Text"]]),"bad.csv")


def test_duplicate_headers_block_instead_of_choosing_arbitrarily():
    with pytest.raises(ImportFailure):
        parse_export(csv_bytes([HEADERS+["Comment HTML"],["A","B","C","D","Other"]]),"duplicate.csv")


def test_formula_cells_block_import_without_evaluating():
    data = workbook_bytes({"Template":[HEADERS,["A","B","C",'=HYPERLINK("https://example.com","text")']]})
    with pytest.raises(ImportFailure) as exc:
        parse_export(data,"formula.xlsx")
    assert "Formula" in exc.value.issues[0]["message"]


def test_blank_and_structure_only_rows_are_visible():
    parsed = parse_export(csv_bytes([HEADERS,["A","","",""],[],["A","B","",""],["A","B","C","text"]]), "structure.csv")
    assert len(parsed["sections"][0]["items"]) == 1
    assert parsed["report"]["counts"]["source_rows"] == 3
    assert parsed["report"]["counts"]["blank_rows"] == 1
    assert "STRUCTURE_ONLY" in {w["code"] for w in parsed["report"]["warnings"]}


def test_multiline_quoted_csv_keeps_exact_cell_whitespace():
    html = ' <p>First, "quoted" &amp; linked.</p>\r\n<p>Second line.</p> '
    parsed = parse_export(csv_bytes([HEADERS,[" A ","B"," C ",html]]), "multiline.csv")
    assert flatten(parsed)[0]["html"] == html
    assert parsed["sections"][0]["name"] == " A "


def test_incomplete_order_does_not_make_up_a_sequence():
    data = csv_bytes([HEADERS+["Order (w/i item)"],["A","B","First","One","2"],["A","B","Second","Two",""]])
    parsed = parse_export(data,"partial.csv")
    assert [c["name"] for c in flatten(parsed)] == ["First","Second"]
    assert "ORDER_FALLBACK" in {w["code"] for w in parsed["report"]["warnings"]}


def test_order_ties_are_stable_and_duplicates_are_not_deduplicated():
    data = csv_bytes([HEADERS+["Order"],["A","B","Same","Same","1"],["A","B","Same","Same","1"]])
    parsed = parse_export(data,"ties.csv")
    assert len(flatten(parsed)) == 2 and [c["row"] for c in flatten(parsed)] == [2,3]
    assert "ORDER_TIE" in {w["code"] for w in parsed["report"]["warnings"]}


@pytest.mark.parametrize("html", ['<script>alert(1)</script><p onclick="evil()">Good</p>', '<a href="javascript:alert(1)">link</a>', '<a href="java&#x09;script:alert(1)">link</a>', '<iframe src="https://example.com"></iframe>', '<svg onload="alert(1)"></svg>'])
def test_unsafe_rich_content_is_retained_but_never_executable(html):
    result = render_html(html)
    assert result["issues"]
    safe = result["safe_html"].lower()
    assert '<script' not in safe and 'onclick=' not in safe and '<iframe' not in safe and 'href="javascript:' not in safe and '<svg' not in safe
    parsed = parse_export(csv_bytes([HEADERS,["A","B","C",html]]),"unsafe.csv")
    assert flatten(parsed)[0]["original_html"] == html


def test_links_styles_and_images_have_explicit_safe_behavior():
    html = '<p style="color: red; position: fixed">Exact</p><a href="https://example.com">Safe link</a><img src="https://example.com/x.png" alt="sample">'
    safe = render_html(html)
    assert 'color: red' in safe["safe_html"] and 'position:' not in safe["safe_html"]
    assert 'href="https://example.com"' in safe["safe_html"]
    assert 'data-source-src="https://example.com/x.png"' in safe["safe_html"]
    assert 'rel="noopener noreferrer"' in safe["safe_html"]


def test_bom_and_header_aliases_are_supported():
    data = csv_bytes([["\ufeff section name ","ITEM NAME","Comment Title","Comment HTML"],["A","B","C","<p>Text</p>"]])
    assert flatten(parse_export(data,"bom.csv"))[0]["html"] == "<p>Text</p>"


def test_oversized_expanded_zip_is_rejected():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as file:
        file.writestr('xl/worksheets/sheet1.xml',b' '* (21*1024*1024))
    with pytest.raises(ImportFailure,match="safety limit"):
        parse_export(stream.getvalue(),"bomb.xlsx")
