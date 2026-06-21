"""
Dependency-free exporters for the License Console.
==================================================
Writes REAL .csv, .xlsx and .pdf files with no third-party libraries (so the
frozen LicenseConsole.exe needs nothing extra bundled). Each function takes
simple headers + rows and produces a file that opens cleanly in Excel / a PDF
viewer — not a "notepad" dump.

  rows: list of rows; each row is a list of cells. A cell may be a str or a
        number (int/float). Numbers land as real numeric cells in Excel.
"""

import datetime
import struct
import zipfile
from pathlib import Path

# --------------------------------------------------------------------------- #
#  CSV
# --------------------------------------------------------------------------- #
import csv as _csv


def write_csv(path, headers, rows):
    # utf-8-sig (BOM) so Excel opens UTF-8 (names, symbols) correctly on Windows.
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = _csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow(["" if c is None else c for c in r])
    return path


# --------------------------------------------------------------------------- #
#  XLSX  (minimal but valid OOXML — inline strings, frozen header, column widths)
# --------------------------------------------------------------------------- #
def _xml_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _col_letter(idx):  # 0 -> A, 26 -> AA
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _sheet_xml(headers, rows):
    ncols = max([len(headers)] + [len(r) for r in rows]) if (headers or rows) else 1
    # sensible column widths
    cols = "".join(
        f'<col min="{i+1}" max="{i+1}" width="{18 if i < 2 else 26 if i == 3 else 16}" customWidth="1"/>'
        for i in range(ncols))

    def cell(col, rownum, value, header=False):
        ref = f"{_col_letter(col)}{rownum}"
        if value is None or value == "":
            return f'<c r="{ref}"/>'
        if _is_number(value) and not header:
            return f'<c r="{ref}"><v>{value}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{_xml_escape(value)}</t></is></c>'

    body = []
    body.append("<row r=\"1\">" + "".join(
        cell(c, 1, headers[c], header=True) for c in range(len(headers))) + "</row>")
    for ri, row in enumerate(rows, start=2):
        body.append(f'<row r="{ri}">' + "".join(
            cell(c, ri, row[c] if c < len(row) else "") for c in range(ncols)) + "</row>")

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        f"<cols>{cols}</cols>"
        f"<sheetData>{''.join(body)}</sheetData>"
        f'<autoFilter ref="A1:{_col_letter(ncols-1)}{len(rows)+1}"/>'
        "</worksheet>")


def write_xlsx(path, headers, rows, sheet_name="Licenses"):
    sheet = _sheet_xml(headers, rows)
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>")
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>")
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{_xml_escape(sheet_name)[:31]}" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>")
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return path


# --------------------------------------------------------------------------- #
#  PDF  (minimal, paginated, landscape — Helvetica standard fonts, no embedding)
# --------------------------------------------------------------------------- #
# Helvetica AFM advance widths (1000-unit em) for measuring text so columns fit.
_HELV_W = {  # only the common glyphs; default 556 for anything else
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667, "'": 191,
    "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333, ".": 278, "/": 278,
    "0": 556, "1": 556, "2": 556, "3": 556, "4": 556, "5": 556, "6": 556, "7": 556,
    "8": 556, "9": 556, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584, "?": 556,
    "@": 1015, "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722, "O": 778,
    "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722, "V": 667, "W": 944,
    "X": 667, "Y": 667, "Z": 611, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556, "o": 556,
    "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556, "v": 500, "w": 722,
    "x": 500, "y": 500, "z": 500, "{": 334, "|": 260, "}": 334, "~": 584,
}


def _text_w(s, size):
    return sum(_HELV_W.get(c, 556) for c in str(s)) * size / 1000.0


def _fit(s, width, size):
    """Truncate s with an ellipsis so it fits within width points."""
    s = str(s)
    if _text_w(s, size) <= width:
        return s
    ell = "…"
    while s and _text_w(s + ell, size) > width:
        s = s[:-1]
    return s + ell


def _pdf_escape(s):
    return str(s).replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def write_pdf(path, headers, rows, title="License Records", subtitle=""):
    # Landscape A4.
    PW, PH = 842.0, 595.0
    margin = 28.0
    x0 = margin
    usable = PW - 2 * margin
    fs = 8.0           # body font size
    hfs = 8.5          # header font size
    row_h = 15.0
    top = PH - margin

    ncols = len(headers)
    # proportional column widths (caller can bias by header length); equal-ish.
    weights = [max(6, len(str(h))) for h in headers]
    wsum = sum(weights)
    widths = [usable * w / wsum for w in weights]
    xs, acc = [], x0
    for w in widths:
        xs.append(acc); acc += w

    # paginate
    header_block = 64.0   # title + column header
    rows_per_page = int((top - margin - header_block) / row_h)
    rows_per_page = max(1, rows_per_page)
    pages = [rows[i:i + rows_per_page] for i in range(0, len(rows), rows_per_page)] or [[]]

    when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    def page_stream(page_rows, page_no, page_total):
        out = []
        # title
        out.append("BT /F2 15 Tf 0.10 0.10 0.16 rg "
                   f"1 0 0 1 {x0:.1f} {top-6:.1f} Tm ({_pdf_escape(title)}) Tj ET")
        sub = subtitle or f"Generated {when}"
        out.append("BT /F1 9 Tf 0.45 0.45 0.5 rg "
                   f"1 0 0 1 {x0:.1f} {top-22:.1f} Tm ({_pdf_escape(sub)}) Tj ET")
        out.append("BT /F1 9 Tf 0.45 0.45 0.5 rg "
                   f"1 0 0 1 {PW-margin-110:.1f} {top-22:.1f} Tm (Page {page_no} of {page_total}) Tj ET")
        # header band
        hy = top - header_block + 6
        out.append(f"0.93 0.93 0.96 rg {x0:.1f} {hy-3:.1f} {usable:.1f} {row_h:.1f} re f")
        out.append("0.10 0.10 0.16 rg")
        for c in range(ncols):
            t = _fit(headers[c], widths[c] - 6, hfs)
            out.append(f"BT /F2 {hfs} Tf 1 0 0 1 {xs[c]+3:.1f} {hy+2:.1f} Tm ({_pdf_escape(t)}) Tj ET")
        # rows
        y = hy - row_h
        for ri, row in enumerate(page_rows):
            if ri % 2 == 1:  # zebra
                out.append(f"0.97 0.97 0.98 rg {x0:.1f} {y-3:.1f} {usable:.1f} {row_h:.1f} re f")
            out.append("0.16 0.16 0.2 rg")
            for c in range(ncols):
                val = row[c] if c < len(row) else ""
                if val is None:
                    val = ""
                t = _fit(val, widths[c] - 6, fs)
                out.append(f"BT /F1 {fs} Tf 1 0 0 1 {xs[c]+3:.1f} {y+2:.1f} Tm ({_pdf_escape(t)}) Tj ET")
            y -= row_h
        return "\n".join(out).encode("latin-1", "replace")

    # assemble objects
    objs = []  # raw bytes per object (1-indexed when written)

    def add(obj_bytes):
        objs.append(obj_bytes)
        return len(objs)  # object number

    # fonts
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")

    page_obj_nums, content_obj_nums = [], []
    total = len(pages)
    for pno, prows in enumerate(pages, start=1):
        stream = page_stream(prows, pno, total)
        cnum = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        content_obj_nums.append(cnum)
        page_obj_nums.append(None)  # placeholder; fill after we know pages-parent num

    # pages parent + page objects (need cross refs)
    pages_num = len(objs) + 1 + 0  # the Pages object number (added next)
    # we will add: Pages, then each Page
    pages_kids_num_start = pages_num + 1
    page_nums = list(range(pages_kids_num_start, pages_kids_num_start + total))
    kids = " ".join(f"{n} 0 R" for n in page_nums)
    add(("<< /Type /Pages /Kids [%s] /Count %d "
         "/MediaBox [0 0 %.0f %.0f] >>" % (kids, total, PW, PH)).encode())
    for i in range(total):
        add(("<< /Type /Page /Parent %d 0 R "
             "/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> "
             "/Contents %d 0 R >>" % (pages_num, f1, f2, content_obj_nums[i])).encode())
    catalog = add(("<< /Type /Catalog /Pages %d 0 R >>" % pages_num).encode())

    # serialize with xref
    buf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0] * (len(objs) + 1)
    for i, ob in enumerate(objs, start=1):
        offsets[i] = len(buf)
        buf += ("%d 0 obj\n" % i).encode() + ob + b"\nendobj\n"
    xref_pos = len(buf)
    buf += ("xref\n0 %d\n" % (len(objs) + 1)).encode()
    buf += b"0000000000 65535 f \n"
    for i in range(1, len(objs) + 1):
        buf += ("%010d 00000 n \n" % offsets[i]).encode()
    buf += ("trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF"
            % (len(objs) + 1, catalog, xref_pos)).encode()

    Path(path).write_bytes(buf)
    return path
