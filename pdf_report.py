# pdf_report.py
from __future__ import annotations

from io import BytesIO
from typing import List, Dict


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_pdf_report(title: str, rows: List[Dict]) -> bytes:
    """
    Pure-Python PDF generator (no external dependencies).
    Renders a simple text report with columns:
      Date | Start Miles | End Miles | Start Time | End Time | Notes
    """
    # Page setup (US Letter, points)
    page_w, page_h = 612, 792  # 8.5x11
    left = 40
    top = page_h - 50
    line_h = 14

    def make_lines() -> list[str]:
        lines = []
        lines.append(title)
        lines.append("")
        header = "Date        Start   End     Start Time   End Time     Notes"
        lines.append(header)
        lines.append("-" * len(header))

        for r in rows:
            d = str(r.get("date", ""))
            sm = f"{float(r.get('start_miles', 0.0)):.2f}"
            em = f"{float(r.get('end_miles', 0.0)):.2f}"
            st = str(r.get("start_time", ""))
            et = str(r.get("end_time", ""))
            notes = (r.get("notes") or "").strip()

            # keep notes sane length so a text line doesn't explode
            if len(notes) > 50:
                notes = notes[:47] + "..."

            # fixed-ish spacing
            line = f"{d:<10}  {sm:>6}  {em:>6}  {st:<10}  {et:<10}  {notes}"
            lines.append(line)

        return lines

    lines = make_lines()

    # paginate
    max_lines_per_page = int((top - 60) // line_h)  # bottom margin ~60
    pages = [lines[i:i + max_lines_per_page] for i in range(0, len(lines), max_lines_per_page)]

    # Build a minimal PDF with one font (Helvetica) and text streams.
    # This is a simple, valid PDF structure.
    out = BytesIO()
    objects: list[bytes] = []
    offsets: list[int] = []

    def add_obj(data: bytes) -> int:
        objects.append(data)
        return len(objects)

    # 1) Catalog
    # 2) Pages
    # 3..n) Page(s)
    # font object
    font_obj_num = add_obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_obj_nums = []

    # Create each page content stream
    content_obj_nums = []
    for page_index, page_lines in enumerate(pages):
        # Build text content stream
        y = top
        stream_lines = ["BT", "/F1 11 Tf", f"{left} {y} Td"]
        first = True
        for ln in page_lines:
            if not first:
                stream_lines.append(f"0 -{line_h} Td")
            first = False
            stream_lines.append(f"({_pdf_escape(ln)}) Tj")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", "ignore")

        content = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        content_obj_nums.append(add_obj(content))

    # Build Pages object after pages are made
    # Placeholder; we’ll fill kids list after creating page objects.
    # We'll create page objects now.
    for i, content_num in enumerate(content_obj_nums):
        page = (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 %d 0 R >> >> "
            b"/Contents %d 0 R >>"
        ) % (font_obj_num, content_num)
        page_obj_nums.append(add_obj(page))

    kids = " ".join([f"{n} 0 R" for n in page_obj_nums]).encode("ascii")
    pages_obj = b"<< /Type /Pages /Kids [ %s ] /Count %d >>" % (kids, len(page_obj_nums))

    # Insert Pages object as object #2 (we haven't created Catalog yet)
    # We'll rebuild objects list in correct order:
    # obj 1: Catalog, obj 2: Pages, others...
    # We already added font + content + pages; easiest is rebuild in a new list.

    # Rebuild:
    old_objects = objects[:]
    objects = []
    offsets = []

    # Object 1: Catalog (references Pages 2)
    add_obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    # Object 2: Pages
    add_obj(pages_obj)
    # Object 3: Font (was font_obj_num in old list; now it's 3)
    add_obj(old_objects[font_obj_num - 1])

    # Now add all content streams and pages, but we must fix references:
    # Font reference becomes 3 0 R
    new_content_nums = []
    new_page_nums = []

    # Add content streams
    old_content_objs = [old_objects[n - 1] for n in content_obj_nums]
    for co in old_content_objs:
        new_content_nums.append(add_obj(co))

    # Add page objects with corrected references
    for idx in range(len(pages)):
        # Page references:
        # Parent = 2, Font = 3, Contents = new_content_nums[idx]
        page = (
            b"<< /Type /Page /Parent 2 0 R "
            b"/MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> "
            b"/Contents %d 0 R >>"
        ) % (new_content_nums[idx])
        new_page_nums.append(add_obj(page))

    # Now we must update Pages object (obj 2) kids to the new page object nums
    kids2 = " ".join([f"{n} 0 R" for n in new_page_nums]).encode("ascii")
    pages_obj2 = b"<< /Type /Pages /Kids [ %s ] /Count %d >>" % (kids2, len(new_page_nums))
    objects[1] = pages_obj2  # replace object #2

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
