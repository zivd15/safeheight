from __future__ import annotations
import os
from datetime import date
from pathlib import Path
from dateutil.relativedelta import relativedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas

from app.config import settings
from app.services.auth import generate_serial

# Palette
DARK   = colors.HexColor("#0F172A")   # deep navy
ACCENT = colors.HexColor("#2563EB")   # modern blue
GOLD   = colors.HexColor("#F59E0B")   # warm gold
SLATE  = colors.HexColor("#1E293B")   # body text
MUTED  = colors.HexColor("#64748B")   # secondary text
LIGHT  = colors.HexColor("#F1F5F9")   # card bg
BORDER = colors.HexColor("#CBD5E1")   # rule color
PILL_BG = colors.HexColor("#EFF6FF")  # scope pill bg

VALIDITY_YEARS = 2


def generate_pdf(
    student_name: str,
    national_id: str,
    employer: str,
    scopes: list[str],
    instructor_name: str,
    license_no: str,
    instructor_sig_path: str | None,
) -> dict:
    Path(settings.CERT_DIR).mkdir(parents=True, exist_ok=True)

    date_issue  = date.today()
    date_expiry = date_issue + relativedelta(years=VALIDITY_YEARS)
    serial = generate_serial(student_name)

    date_issue_str  = date_issue.strftime("%d/%m/%Y")
    date_expiry_str = date_expiry.strftime("%d/%m/%Y")

    safe = "".join(ch if ch.isalnum() else "_" for ch in student_name)[:30]
    filename = f"{serial}_{safe}.pdf"
    path = os.path.join(settings.CERT_DIR, filename)

    w, h = A4
    mx = 18 * mm
    c = rl_canvas.Canvas(path, pagesize=A4)

    # ── White background ──────────────────────────────────────────────────────
    c.setFillColor(colors.white)
    c.rect(0, 0, w, h, fill=1, stroke=0)

    # ── Top header strip ──────────────────────────────────────────────────────
    hdr_h = 13 * mm
    c.setFillColor(DARK)
    c.rect(0, h - hdr_h, w, hdr_h, fill=1, stroke=0)

    # Gold accent line below header
    c.setFillColor(GOLD)
    c.rect(0, h - hdr_h - 2 * mm, w, 2 * mm, fill=1, stroke=0)

    # Brand text inside header
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(mx, h - 9 * mm, "SAFEHEIGHT")
    c.setFont("Helvetica", 8)
    c.setFillColor(GOLD)
    c.drawRightString(w - mx, h - 9 * mm, "Working at Height Certification Authority")

    # ── Left accent bar ───────────────────────────────────────────────────────
    bar_top    = h - hdr_h - 2 * mm
    bar_bottom = 10 * mm   # sits just above footer
    c.setFillColor(ACCENT)
    c.rect(0, bar_bottom, 5 * mm, bar_top - bar_bottom, fill=1, stroke=0)

    # ── Certificate title ─────────────────────────────────────────────────────
    y = h - hdr_h - 2 * mm - 18 * mm

    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(DARK)
    c.drawCentredString(w / 2, y, "CERTIFICATE OF COMPETENCY")

    y -= 7 * mm
    c.setFont("Helvetica", 9.5)
    c.setFillColor(MUTED)
    c.drawCentredString(w / 2, y, "Working at Height  ·  Modular General Training")

    y -= 6 * mm
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    c.line(mx + 10 * mm, y, w - mx - 10 * mm, y)

    # ── Recipient block ───────────────────────────────────────────────────────
    y -= 10 * mm
    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(MUTED)
    c.drawCentredString(w / 2, y, "This is to certify that")

    y -= 11 * mm
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(DARK)
    c.drawCentredString(w / 2, y, student_name)

    # Accent underline beneath name
    name_w = c.stringWidth(student_name, "Helvetica-Bold", 22)
    ux = w / 2 - name_w / 2
    y -= 3 * mm
    c.setStrokeColor(ACCENT)
    c.setLineWidth(1.8)
    c.line(ux, y, ux + name_w, y)

    y -= 8 * mm
    c.setFont("Helvetica", 9.5)
    c.setFillColor(MUTED)
    c.drawCentredString(w / 2, y, "has successfully completed the required training and assessment")

    # ── Info cards (2 × 2 grid) ───────────────────────────────────────────────
    y -= 14 * mm
    gap    = 4 * mm
    card_h = 17 * mm
    card_w = (w - 2 * mx - gap) / 2

    def info_card(cx, cy, label, value):
        c.setFillColor(LIGHT)
        c.roundRect(cx, cy - card_h, card_w, card_h, 2.5 * mm, fill=1, stroke=0)
        c.setFont("Helvetica", 7)
        c.setFillColor(MUTED)
        c.drawString(cx + 4 * mm, cy - 5.5 * mm, label.upper())
        # fit value in card
        val = str(value) if value else "—"
        max_w = card_w - 8 * mm
        c.setFont("Helvetica-Bold", 10.5)
        while c.stringWidth(val, "Helvetica-Bold", 10.5) > max_w and len(val) > 5:
            val = val[:-2] + "…"
        c.setFillColor(SLATE)
        c.drawString(cx + 4 * mm, cy - 13 * mm, val)

    info_card(mx, y, "ID Number", national_id)
    info_card(mx + card_w + gap, y, "Employer / Organisation", employer or "—")
    y -= card_h + gap
    info_card(mx, y, "Date of Issue", date_issue_str)
    info_card(mx + card_w + gap, y, "Valid Until", date_expiry_str)

    # Serial below cards
    y -= card_h + 7 * mm
    c.setFont("Helvetica", 8)
    c.setFillColor(MUTED)
    c.drawCentredString(w / 2, y, f"Certificate Serial  ·  {serial}")

    # ── Scopes section ────────────────────────────────────────────────────────
    y -= 11 * mm
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(ACCENT)
    c.drawString(mx, y, "AUTHORIZED TRAINING SCOPES")
    y -= 3.5 * mm
    c.setStrokeColor(ACCENT)
    c.setLineWidth(0.5)
    c.line(mx, y, w - mx, y)
    y -= 8 * mm

    # Pill layout
    pill_h   = 6.5 * mm
    pad_x    = 4 * mm
    gap_x    = 2.5 * mm
    gap_y    = 3 * mm
    row_x    = mx
    c.setFont("Helvetica", 8)

    for scope in scopes:
        pill_w = c.stringWidth(scope, "Helvetica", 8) + 2 * pad_x
        if row_x + pill_w > w - mx and row_x > mx:
            row_x  = mx
            y     -= pill_h + gap_y
        # pill background, no border
        c.setFillColor(PILL_BG)
        c.roundRect(row_x, y - pill_h + 1.5 * mm, pill_w, pill_h - 1.5 * mm,
                    2 * mm, fill=1, stroke=0)
        # pill text in black
        c.setFillColor(SLATE)
        c.drawString(row_x + pad_x, y - pill_h + 3.8 * mm, scope)
        row_x += pill_w + gap_x

    y -= pill_h + 10 * mm

    # ── Divider ───────────────────────────────────────────────────────────────
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    c.line(mx, y, w - mx, y)
    y -= 9 * mm

    # ── Instructor block ──────────────────────────────────────────────────────
    c.setFont("Helvetica", 7)
    c.setFillColor(MUTED)
    c.drawString(mx, y, "LEAD INSTRUCTOR")

    y -= 6 * mm
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(SLATE)
    c.drawString(mx, y, instructor_name)

    y -= 5.5 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawString(mx, y, f"License No.  {license_no}")

    # Signature on the right side
    if instructor_sig_path and os.path.exists(instructor_sig_path):
        try:
            sig_w = 44 * mm
            sig_h = 18 * mm
            sig_x = w - mx - sig_w
            sig_y = y - 10 * mm
            c.drawImage(instructor_sig_path, sig_x, sig_y,
                        width=sig_w, height=sig_h,
                        preserveAspectRatio=True, mask="auto")
            c.setStrokeColor(BORDER)
            c.setLineWidth(0.4)
            c.line(sig_x, sig_y - 1 * mm, sig_x + sig_w, sig_y - 1 * mm)
            c.setFont("Helvetica", 7)
            c.setFillColor(MUTED)
            c.drawCentredString(sig_x + sig_w / 2, sig_y - 4 * mm, "Authorized Signature")
        except Exception:
            pass

    # ── Bottom footer strip ───────────────────────────────────────────────────
    footer_h = 10 * mm
    c.setFillColor(DARK)
    c.rect(0, 0, w, footer_h, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(0, footer_h, w, 1.5 * mm, fill=1, stroke=0)

    c.setFont("Helvetica", 7)
    c.setFillColor(colors.white)
    c.drawCentredString(w / 2, 3.5 * mm,
        f"Serial: {serial}  ·  Verify at: {settings.BASE_URL}  ·  Valid until: {date_expiry_str}")

    c.save()
    return {
        "filename": filename,
        "path": path,
        "serial": serial,
        "date_issue": date_issue_str,
        "date_expiry": date_expiry_str,
    }
