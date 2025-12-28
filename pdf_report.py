# pdf_report.py
from __future__ import annotations

from io import BytesIO
from typing import List, Dict


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_text(text: str, width: int) -> list[str]:
    """Simple word wrap."""
    words = (text or "").split()
    if not words:
        return [""]
    lines = []
    line = words[0]
    for w in words[1:]:
        if len(line) + 1 + len(w) <= width:
            line += " " + w
        else:
            lines.append(line)
            line = w
    lines.append(line)
    return lines


def build_pdf_report(title: str, rows: List[Dict]) -> bytes:
    """
    Pure-Python PDF generator (no external dependencies).
    Produces a readable fixed-width report with wrapped notes.
    Expected keys per row:
      date, start_miles, end_miles, start_time, end_time, notes
    """

    # Letter in points
    page_w, page_h = 612, 792
    left = 40
    top = page_h - 60
    bottom = 55

    # Fonts
    # We'll use built-in PDF base fonts: Helvetica + Courier
    title_font = "Helvetica-Bold"
    header_font = "Helvetica-Bold"
    body_font = "Courier"  # mono font for aligned columns

    title_size = 16
    header_size = 11
    body_size = 10

    # Line spacing
    line_h = 14

    # Column widths (characters) for mono body font
    # Tune these if you want wider Notes, etc.
    COL_DATE = 10
    COL_MILES = 10  # fits 76000.00
    COL_TIME = 9    # fits "8:00 AM"
    COL_NOTES = 40  # wrap notes

    def fmt_row(r: Dict) -> tuple[str, list[str]]:
        d = str(r.get("date", ""))[:COL_DATE]
        sm = f"{float(r.get('start_miles', 0.0)):.2f}"
        em = f"{float(r.get('end_miles', 0.0)):.2f}"
        st = str(r.get("start_time", ""))
        et = str(r.get("end_time", ""))

        # pad/trim to fixed widths
        base = (
            f"{d:<{COL_DATE}}  "
            f"{sm:>{COL_MILES}}  "
            f"{em:>{COL_MILES}}  "
            f"{st:<{COL_TIME}}  "
            f"{et:<{COL_TIME}}  "
        )

        notes = (r.get("notes") or "").strip()
        wrapped_notes = _wrap_text(notes, COL_NOTES)
        return base, wrapped_notes

    # Build printable "logical lines" including wrapping notes
    logical_lines: list[tuple[str, str]] = []  # (kind, text) kind: title/header/body/divider

    logical_lines.append(("title", title))
    logical_lines.append(("spacer", ""))

    # Header (looks good even if body is mono)
    header = (
        f"{'Date':<{COL_DATE}}  "
        f"{'Start':>{COL_MILES}}  "
        f"{'End':>{COL_MILES}}  "
        f"{'Start':<{COL_TIME}}  "
        f"{'End':<{COL_TIME}}  "
        f"{'Notes'}"
    )
    logical_lines.append(("header", header))
    logical_lines.append(("divider", "-" * (COL_DATE + 2 + COL_MILES + 2 + COL_MILES + 2 + COL_TIME + 2 + COL_TIME + 2 + COL_NOTES)))

    for r in rows:
        base, notes_lines = fmt_row(r)
        # first line includes first chunk of notes
        first_notes = notes_lines[0] if notes_lines else ""
        logical_lines.append(("body", base + first_notes))

        # additional wrapped notes lines (indent under notes area)
        for extra in notes_lines[1:]:
            indent = " " * (COL_DATE + 2 + COL_MILES + 2 + COL_MILES + 2 + COL_TIME + 2 + COL_TIME + 2)
            logical_lines.append(("body", indent + extra))

        # divider between records for readability
        logical_lines.append(("spacer", ""))

    # Pagination: estimate how many lines fit
    usable_h = top - bottom
    max_lines_per_page = int(usable_h // line_h)
    pages = [logical_lines[i:i + max_lines_per_page] for i in range(0, len(logical_lines), max_lines_per_page)]

    # ---- Minimal PDF building ----
    out = BytesIO()
    objects: list[bytes] = []
    offsets: list[int] = []

    def add_obj(data: bytes) -> int:
        objects.append(data)
        return len(objects)

    # Font objects
    font_title = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    font_header = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    font_body = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")

    # Build content streams for each page
    content_obj_nums = []
    for page in pages:
        y = top

        # Start text
        parts = ["BT"]
        parts.append(f"{left} {y} Td")

        for kind, text in page:
            if kind == "title":
                parts.append(f"/F1 {title_size} Tf")
            elif kind == "header":
                parts.append(f"/F2 {header_size} Tf")
            elif kind in ("body", "divider"):
                parts.append(f"/F3 {body_size} Tf")
            else:  # spacer
                parts.append(f"/F3 {body_size} Tf")

            parts.append(f"({_pdf_escape(text)}) Tj")
            parts.append(f"0 -{line_h} Td")
            y -= line_h

        parts.append("ET")
        stream = "\n".join(parts).encode("latin-1", "ignore")

        content = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        content_obj_nums.append(add_obj(content))

    # Page objects (we'll rebuild to fix references)
    page_obj_nums = []
    for content_num in content_obj_nums:
        page = (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R /F3 %d 0 R >> >> "
            b"/Contents %d 0 R >>"
        ) % (font_title, font_header, font_body, content_num)
        page_obj_nums.append(add_obj(page))

    # Now rebuild objects so Catalog=1 and Pages=2 (clean)
    old_objects = objects[:]
    objects = []
    offsets = []

    # Catalog
    add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")

    # Pages placeholder (we'll set kids after page objects are re-added)
    add_obj(b"<< /Type /Pages /Kids [] /Count 0 >>")

    # Re-add fonts as objects 3,4,5
    add_obj(old_objects[font_title - 1])
    add_obj(old_objects[font_header - 1])
    add_obj(old_objects[font_body - 1])

    # Re-add content streams
    new_content_nums = []
    old_content_objs = [old_objects[n - 1] for n in content_obj_nums]
    for co in old_content_objs:
        new_content_nums.append(add_obj(co))

    # Re-add pages with corrected font refs (3/4/5) and content refs
    new_page_nums = []
    for idx in range(len(pages)):
        page = (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
            b"/Contents %d 0 R >>"
        ) % (new_content_nums[idx])
        new_page_nums.append(add_obj(page))

    # Update Pages object (obj 2)
    kids = " ".join([f"{n} 0 R" for n in new_page_nums]).encode("ascii")
    pages_obj = b"<< /Type /Pages /Kids [ %s ] /Count %d >>" % (kids, len(new_page_nums))
    objects[1] = pages_obj

    # Write PDF
    out.write(b"%PDF-1.4\n")
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode("ascii"))
        out.write(obj)
        out.write(b"\nendobj\n")

    xref_pos = out.tell()
    out.write(b"xref\n")
    out.write(f"0 {len(objects)+1}\n".encode("ascii"))
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode("ascii"))

    out.write(b"trailer\n")
    out.write(f"<< /Size {len(objects)+1} /Root 1 0 R >>\n".encode("ascii"))
    out.write(b"startxref\n")
    out.write(f"{xref_pos}\n".encode("ascii"))
    out.write(b"%%EOF\n")

    return out.getvalue()

