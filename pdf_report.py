# pdf_report.py
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def build_pdf_report(title: str, rows: list[dict]) -> bytes:
    """
    rows: list of dicts with keys:
      date, start_miles, end_miles, start_time, end_time, notes
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    x = 40
    y = height - 50

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, title)
    y -= 28

    # Column headers
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x, y, "Date")
    c.drawString(x + 80, y, "Start Miles")
    c.drawString(x + 160, y, "End Miles")
    c.drawString(x + 235, y, "Start Time")
    c.drawString(x + 315, y, "End Time")
    c.drawString(x + 395, y, "Notes")
    y -= 12

    c.setFont("Helvetica", 10)
    c.line(x, y, width - 40, y)
    y -= 16

    for r in rows:
        if y < 70:
            c.showPage()
            y = height - 50

            c.setFont("Helvetica-Bold", 10)
            c.drawString(x, y, "Date")
            c.drawString(x + 80, y, "Start Miles")
            c.drawString(x + 160, y, "End Miles")
            c.drawString(x + 235, y, "Start Time")
            c.drawString(x + 315, y, "End Time")
            c.drawString(x + 395, y, "Notes")
            y -= 12

            c.setFont("Helvetica", 10)
            c.line(x, y, width - 40, y)
            y -= 16

        notes = (r.get("notes") or "")
        if len(notes) > 35:
            notes = notes[:32] + "..."

        c.drawString(x, y, str(r.get("date", "")))
        c.drawString(x + 80, y, f"{float(r.get('start_miles', 0.0)):.2f}")
        c.drawString(x + 160, y, f"{float(r.get('end_miles', 0.0)):.2f}")
        c.drawString(x + 235, y, str(r.get("start_time", "")))
        c.drawString(x + 315, y, str(r.get("end_time", "")))
        c.drawString(x + 395, y, notes)
        y -= 14

    c.showPage()
    c.save()
    return buf.getvalue()
