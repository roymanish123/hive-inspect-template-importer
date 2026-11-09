"""Spreadsheet -> ordered tree + immutable per-row evidence. No generative mapping."""
import csv
import hashlib
import io
import math
import re
import zipfile
from datetime import date, datetime
from pathlib import Path

import openpyxl
import xlrd

from .rich_text import render_html

MAX_BYTES = 3 * 1024 * 1024
MAX_ROWS = 12000
MAX_COLS = 100
MAX_TEXT = 200000
REQUIRED = {"section", "item", "comment_name", "comment_text"}
ALIASES = {"section name": "section", "section": "section", "item name": "item", "item": "item",
           "comment name": "comment_name", "comment title": "comment_name", "comment text": "comment_text",
           "comment html": "comment_text", "comment type": "comment_type", "category": "category",
           "order": "order", "answer type": "answer_type"}


class ImportFailure(ValueError):
    def __init__(self, message, issues=None):
        super().__init__(message)
        self.issues = issues or []


def canonical(value):
    value = re.sub(r"\s*\([^)]*\)", "", str(value).replace("\ufeff", "")).strip().lower()
    return ALIASES.get(re.sub(r"\s+", " ", value))


def text(value):
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ImportFailure("A cell contains a non-finite number.")
        if value.is_integer():
            return str(int(value))
    return str(value)


def _sheets(data, filename):
    ext = Path(filename).suffix.lower()
    if ext == ".csv":
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ImportFailure("CSV must use UTF-8 encoding. Export the workbook as XLSX instead.") from exc
        csv.field_size_limit(MAX_TEXT)
        try:
            dialect = csv.Sniffer().sniff(content[:16000], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        try:
            rows = []
            for row in csv.reader(io.StringIO(content, newline=""), dialect=dialect, strict=True):
                rows.append(row)
                if len(rows) > MAX_ROWS or len(row) > MAX_COLS:
                    raise ImportFailure("Spreadsheet exceeds 12,000 rows or 100 columns.")
            return [{"name": "CSV", "rows": rows, "issues": [], "formulas": []}]
        except csv.Error as exc:
            raise ImportFailure(f"Could not parse CSV: {exc}") from exc
    if ext == ".xlsx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                parts = archive.infolist()
                if len(parts) > 2000 or sum(p.file_size for p in parts) > 40 * 1024 * 1024:
                    raise ImportFailure("Workbook expands beyond the 40 MB safety limit.")
                for part in parts:
                    if part.file_size > 20 * 1024 * 1024:
                        raise ImportFailure("A workbook component exceeds the 20 MB safety limit.")
            book = openpyxl.load_workbook(io.BytesIO(data), read_only=False, data_only=False, keep_links=False)
            if len(book.worksheets) > 25:
                raise ImportFailure("Workbook has more than 25 sheets.")
            result = []
            total = 0
            for sheet in book:
                total += sheet.max_row
                if total > MAX_ROWS or sheet.max_column > MAX_COLS:
                    raise ImportFailure("Spreadsheet exceeds 12,000 total rows or 100 columns.")
                rows, formulas, issues = [], [], []
                for row in sheet.iter_rows():
                    rows.append([text(c.value) for c in row])
                    formulas.extend((c.row, c.column) for c in row if c.data_type in {"f", "e"})
                    for c in row:
                        if c.hyperlink or c.comment:
                            issues.append({"row": c.row, "code": "CELL_ANNOTATION", "message": "Cell hyperlink/annotation is not mapped; original workbook is retained."})
                if sheet.merged_cells.ranges:
                    issues.append({"code": "MERGED_CELLS", "message": "Merged cells found. Only anchor values are read; blank hierarchy cells use visible carry-forward rules."})
                if sheet.sheet_state != "visible":
                    issues.append({"code": "HIDDEN_SHEET", "message": "Hidden sheet was included in the audit."})
                if sheet._images or sheet._charts:
                    issues.append({"code": "WORKBOOK_OBJECT", "message": "Embedded workbook objects are not mapped; original workbook is retained."})
                result.append({"name": sheet.title, "rows": rows, "issues": issues, "formulas": formulas})
            book.close()
            return result
        except ImportFailure:
            raise
        except Exception as exc:
            raise ImportFailure("Could not read XLSX. Upload a valid, unencrypted Spectora spreadsheet.") from exc
    if ext == ".xls":
        try:
            book = xlrd.open_workbook(file_contents=data)
            if book.nsheets > 25:
                raise ImportFailure("Workbook has more than 25 sheets.")
            result = []
            total = 0
            for sheet in book.sheets():
                total += sheet.nrows
                if total > MAX_ROWS or sheet.ncols > MAX_COLS:
                    raise ImportFailure("Spreadsheet exceeds 12,000 total rows or 100 columns.")
                result.append({"name": sheet.name, "rows": [[text(v) for v in sheet.row_values(r)] for r in range(sheet.nrows)],
                    "issues": [{"code": "LEGACY_XLS", "message": "XLS cached cell values are read; formula detection and workbook objects require XLSX. Original file is retained."}], "formulas": []})
            return result
        except ImportFailure:
            raise
        except Exception as exc:
            raise ImportFailure("Could not read XLS. Upload an unencrypted XLS/XLSX workbook.") from exc
    raise ImportFailure("Unsupported file type. Upload .xlsx, .xls, or UTF-8 .csv with HTML-text comment cells.")


def parse_export(data, filename):
    if not data:
        raise ImportFailure("The uploaded file is empty.")
    if len(data) > MAX_BYTES:
        raise ImportFailure("File exceeds the 3 MB upload limit.")
    sheets = _sheets(data, filename)
    sections, evidence, warnings, errors, summaries = [], [], [], [], []
    counts = {"source_rows": 0, "mapped_rows": 0, "retained_rows": 0, "blank_rows": 0, "comments": 0, "items": 0, "sections": 0}

    def warn(sheet, row, code, message):
        warnings.append({"sheet": sheet, "row": row, "code": code, "message": message})

    for sheet in sheets:
        name, rows = sheet["name"], sheet["rows"]
        header_index = None
        for idx, row in enumerate(rows[:20]):
            if REQUIRED <= {canonical(v) for v in row}:
                header_index = idx
                break
        for issue in sheet["issues"]:
            warnings.append({"sheet": name, "row": None, **issue})
        if header_index is None:
            nonempty = [(r + 1, row) for r, row in enumerate(rows) if any(v != "" for v in row)]
            if nonempty:
                warn(name, None, "UNMAPPED_SHEET", "Sheet has no supported header; all nonempty rows are retained as unmapped evidence.")
            for r, row in nonempty:
                evidence.append({"sheet": name, "row": r, "values": row, "status": "retained", "reason": "No supported header"})
            counts["source_rows"] += len(nonempty)
            counts["retained_rows"] += len(nonempty)
            summaries.append({"name": name, "header_row": None, "mapped": 0, "retained": len(nonempty)})
            continue
        headers = [text(v) for v in rows[header_index]]
        mapping = {}
        for col, h in enumerate(headers):
            key = canonical(h)
            if key and key in mapping:
                errors.append({"sheet": name, "row": header_index + 1, "message": f"Duplicate mapped header '{h}'."})
            if key:
                mapping[key] = col
        if any(r > header_index + 1 for r, c in sheet["formulas"]):
            errors.append({"sheet": name, "message": "Formula or Excel error cells found in data. Export literal values; formulas are not evaluated."})
        for idx, row in enumerate(rows[:header_index]):
            if any(v != "" for v in row):
                evidence.append({"sheet": name, "row": idx + 1, "values": row, "status": "retained", "reason": "Preamble before header"})
                counts["source_rows"] += 1
                counts["retained_rows"] += 1
                warn(name, idx + 1, "PREAMBLE", "Preamble row retained outside the template tree.")
        current_section = current_item = None
        seen_sections = set()
        mapped = 0
        for idx, row in enumerate(rows[header_index + 1:], start=header_index + 2):
            row = [text(v) for v in row]
            if not any(v != "" for v in row):
                counts["blank_rows"] += 1
                continue
            counts["source_rows"] += 1
            if any(len(v) > MAX_TEXT for v in row):
                errors.append({"sheet": name, "row": idx, "message": "A cell exceeds the 200,000 character limit."})
                continue
            if len(row) > len(headers) and any(row[len(headers):]):
                errors.append({"sheet": name, "row": idx, "message": "Row contains values beyond the header columns."})
            get = lambda key: row[mapping[key]] if key in mapping and mapping[key] < len(row) else ""
            sec_name, item_name = get("section"), get("item")
            comment_name, body = get("comment_name"), get("comment_text")
            if not sec_name:
                if current_section:
                    sec_name = current_section["name"]
                    warn(name, idx, "INHERITED_SECTION", "Blank section cell inherits preceding section in this sheet.")
                else:
                    errors.append({"sheet": name, "row": idx, "message": "Missing section with no preceding section to inherit."})
                    continue
            if current_section is None or current_section["name"] != sec_name:
                if sec_name in seen_sections:
                    warn(name, idx, "REPEATED_SECTION", "Section name reappears after another section; kept as a distinct section to preserve order.")
                seen_sections.add(sec_name)
                current_section = {"name": sec_name, "position": len(sections), "sheet": name, "row": idx, "items": []}
                sections.append(current_section)
                current_item = None
            entry = {"sheet": name, "row": idx, "values": row, "status": "mapped", "section_position": current_section["position"]}
            if not item_name and (comment_name or body):
                if current_item:
                    item_name = current_item["name"]
                    warn(name, idx, "INHERITED_ITEM", "Blank item cell inherits preceding item in this section.")
                else:
                    errors.append({"sheet": name, "row": idx, "message": "Comment has no item, and no preceding item in this section."})
                    continue
            if item_name:
                if current_item is None or current_item["name"] != item_name:
                    current_item = {"name": item_name, "position": len(current_section["items"]), "sheet": name, "row": idx, "comments": []}
                    current_section["items"].append(current_item)
                    counts["items"] += 1
                entry["item_position"] = current_item["position"]
            if comment_name or body:
                if not comment_name:
                    warn(name, idx, "UNTITLED_COMMENT", "Empty comment name preserved; editor shows an Untitled comment label.")
                rich = render_html(body)
                for issue in rich["issues"]:
                    warn(name, idx, "RICH_CONTENT", issue)
                metadata = {headers[c] or f"Column {c + 1}": value for c, value in enumerate(row[:len(headers)]) if c not in [mapping[k] for k in REQUIRED] and value != ""}
                comment = {"name": comment_name, "html": body, "original_html": body, "position": len(current_item["comments"]),
                           "sheet": name, "row": idx, "metadata": metadata, "type": get("comment_type"), "category": get("category"), "order": get("order")}
                current_item["comments"].append(comment)
                entry["comment_source_key"] = f"{name}:{idx}"
                counts["comments"] += 1
                if comment["type"] not in {"", "info", "limit", "defect"}:
                    warn(name, idx, "COMMENT_TYPE", f"Unrecognized comment type '{comment['type']}' retained as metadata.")
            else:
                warn(name, idx, "STRUCTURE_ONLY", "Row without comment text or name is preserved as structure; all cells remain in source evidence.")
            behavior_columns = [mapping[k] for k in REQUIRED | {"order", "comment_type"} if k in mapping]
            unknown = [headers[c] or f"Column {c + 1}" for c, v in enumerate(row[:len(headers)]) if v != "" and c not in behavior_columns]
            if unknown:
                warn(name, idx, "METADATA_ONLY", "Additional columns retained, without behavior mapping: " + ", ".join(unknown))
            evidence.append(entry)
            counts["mapped_rows"] += 1
            mapped += 1
        summaries.append({"name": name, "header_row": header_index + 1, "mapped": mapped, "retained": 0})
    if errors:
        raise ImportFailure("Import blocked. Fix the listed rows; no template was saved.", errors)
    if counts["mapped_rows"] == 0:
        raise ImportFailure("No template rows found. Required headers: Section Name, Item Name, Comment Name, Comment Text.", warnings)
    # Explicit order is authoritative when EVERY comment in an item supplies a valid number.
    # Otherwise retain sheet row order and expose the ambiguity rather than guessing.
    for sec in sections:
        for item in sec["items"]:
            comments = item["comments"]
            orders = [c["order"] for c in comments]
            if any(orders):
                try:
                    numeric = [float(o) for o in orders]
                    if not all(math.isfinite(o) for o in numeric):
                        raise ValueError
                    comments.sort(key=lambda c: float(c["order"]))
                    if len(numeric) != len(set(numeric)):
                        warn(item["sheet"], item["row"], "ORDER_TIE", "Equal order values use original row order as a stable tie-breaker.")
                except (ValueError, TypeError):
                    warn(item["sheet"], item["row"], "ORDER_FALLBACK", "Incomplete/invalid order values: original row order retained for this item.")
            for position, comment in enumerate(comments):
                comment["position"] = position
    counts["sections"] = len(sections)
    assert counts["source_rows"] == counts["mapped_rows"] + counts["retained_rows"]
    return {"sections": sections, "rows": evidence, "report": {"filename": Path(filename).name, "sha256": hashlib.sha256(data).hexdigest(),
        "counts": counts, "warnings": warnings, "sheets": summaries, "missing_from_export": [
            "Content not present in this file cannot be reconstructed (for example, settings or assets excluded by the source export).",
            "Remote image availability and original report appearance cannot be verified from URL strings alone."],
        "policy": "Text cells are retained verbatim. Sections/items follow sheet order. Complete numeric Order values determine comment order; ties use source row order. All other cells remain in source evidence."}}
