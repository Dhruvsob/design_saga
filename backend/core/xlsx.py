"""Minimal, dependency-free .xlsx writer (Office Open XML).

Enough for accounting exports: several sheets, a bold frozen header row,
numbers stored as numbers and text stored as inline strings.

Text is never written as a formula (no <f> elements are produced), so a value
such as "=HYPERLINK(...)" or "-500" is shown literally and cannot execute when
the workbook is opened - the spreadsheet formula-injection risk does not apply.
"""
import io
import math
import re
import zipfile
from typing import Iterable, List, Sequence, Tuple
from xml.sax.saxutils import escape

_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")
# XML 1.0 forbids most control characters; drop them rather than corrupt the file.
_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _col(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref: str, value, style: int = 0) -> str:
    st = f' s="{style}"' if style else ""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        value = "Yes" if value else "No"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            return ""
        return f'<c r="{ref}"{st}><v>{repr(round(float(value), 6)) if isinstance(value, float) else value}</v></c>'
    text = _XML_ILLEGAL.sub("", str(value))[:32000]
    return f'<c r="{ref}"{st} t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def _sheet_xml(rows: Sequence[Sequence], widths: List[int]) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
           'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>']
    if widths:
        out.append("<cols>" + "".join(
            f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths)) + "</cols>")
    out.append("<sheetData>")
    for r, row in enumerate(rows):
        cells = "".join(_cell(f"{_col(c)}{r + 1}", v, 1 if r == 0 else 0) for c, v in enumerate(row))
        out.append(f'<row r="{r + 1}">{cells}</row>')
    out.append("</sheetData></worksheet>")
    return "".join(out)


def _widths(rows: Sequence[Sequence]) -> List[int]:
    widths: List[int] = []
    for row in rows[:400]:
        for i, v in enumerate(row):
            n = min(60, max(8, len(str(v if v is not None else "")) + 2))
            if i >= len(widths):
                widths.append(n)
            elif n > widths[i]:
                widths[i] = n
    return widths


def safe_sheet_name(name: str, used: set) -> str:
    base = _BAD_SHEET_CHARS.sub(" ", str(name or "Sheet")).strip()[:31] or "Sheet"
    candidate, i = base, 2
    while candidate.lower() in used:
        suffix = f" ({i})"
        candidate = base[:31 - len(suffix)] + suffix
        i += 1
    used.add(candidate.lower())
    return candidate


def build_xlsx(sheets: Iterable[Tuple[str, Sequence[Sequence]]]) -> bytes:
    sheets = list(sheets)
    used: set = set()
    names = [safe_sheet_name(n, used) for n, _ in sheets]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                             'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                             for i in range(len(sheets)))
                   + "</Types>")
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '</Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n, {chr(34): "&quot;"})}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
                             for i, n in enumerate(names))
                   + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                             f'Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(sheets)))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   + "</Relationships>")
        z.writestr("xl/styles.xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
                   '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
                   '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
                   '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
                   '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                   '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                   '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
                   '</styleSheet>')
        for i, (_, rows) in enumerate(sheets):
            rows = list(rows)
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", _sheet_xml(rows, _widths(rows)))
    return buf.getvalue()
