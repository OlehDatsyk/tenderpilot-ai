"""Export reports as PDF (ReportLab), DOCX (python-docx) or CSV.

Reports are built once as a neutral block structure and rendered by each format, so PDF and DOCX
always contain the same data. AI-generated and demo content is labelled in every export.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from xml.sax.saxutils import escape

Block = tuple  # ("h", text) | ("p", text) | ("bullets", [str]) | ("kv", [(k, v)]) | ("table", headers, rows) | ("notice", text)


@dataclass
class Report:
    title: str
    subtitle: str
    blocks: list[Block] = field(default_factory=list)

    def h(self, text: str) -> None:
        self.blocks.append(("h", text))

    def p(self, text: str) -> None:
        if text:
            self.blocks.append(("p", text))

    def bullets(self, items: list[str]) -> None:
        if items:
            self.blocks.append(("bullets", [str(i) for i in items]))

    def kv(self, pairs: list[tuple[str, str]]) -> None:
        self.blocks.append(("kv", pairs))

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        self.blocks.append(("table", headers, rows))

    def notice(self, text: str) -> None:
        self.blocks.append(("notice", text))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "tender"


def generated_stamp() -> str:
    return datetime.now(UTC).strftime("Generated %d %b %Y %H:%M UTC by TenderPilot AI")


_PDF_REPLACEMENTS = {"→": "->", "—": "-", "–": "-", "•": "-", "…": "...", " ": " "}


def _pdf_text(text: str) -> str:
    for a, b in _PDF_REPLACEMENTS.items():
        text = text.replace(a, b)
    text = text.encode("cp1252", errors="replace").decode("cp1252")
    return escape(text).replace("\n", "<br/>")


def render_pdf(report: Report) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title=report.title, author="TenderPilot AI"
    )
    ss = getSampleStyleSheet()
    navy = colors.HexColor("#0f1f3d")
    title = ParagraphStyle("t", parent=ss["Title"], textColor=navy, alignment=TA_LEFT, fontSize=18, spaceAfter=4)
    sub = ParagraphStyle("s", parent=ss["Normal"], textColor=colors.HexColor("#5b6478"), fontSize=9, spaceAfter=10)
    h = ParagraphStyle("h", parent=ss["Heading2"], textColor=navy, fontSize=12.5, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=9.5, leading=13)
    small = ParagraphStyle("sm", parent=body, fontSize=8, leading=10)
    notice = ParagraphStyle(
        "n",
        parent=body,
        backColor=colors.HexColor("#fff7e0"),
        borderColor=colors.HexColor("#e0b84f"),
        borderWidth=0.6,
        borderPadding=5,
        spaceBefore=4,
        spaceAfter=8,
        fontSize=8.5,
    )

    story: list = [Paragraph(_pdf_text(report.title), title), Paragraph(_pdf_text(report.subtitle), sub)]
    width = A4[0] - 36 * mm
    for block in report.blocks:
        kind = block[0]
        if kind == "h":
            story.append(Paragraph(_pdf_text(block[1]), h))
        elif kind == "p":
            story.append(Paragraph(_pdf_text(block[1]), body))
            story.append(Spacer(1, 4))
        elif kind == "notice":
            story.append(Paragraph(_pdf_text(block[1]), notice))
        elif kind == "bullets":
            story.append(
                ListFlowable([ListItem(Paragraph(_pdf_text(i), body), leftIndent=10) for i in block[1]], bulletType="bullet", start="-", leftIndent=10)
            )
            story.append(Spacer(1, 4))
        elif kind == "kv":
            data = [[Paragraph(f"<b>{_pdf_text(k)}</b>", body), Paragraph(_pdf_text(v or "-"), body)] for k, v in block[1]]
            t = Table(data, colWidths=[width * 0.3, width * 0.7])
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d9dee8"))]))
            story.append(t)
        elif kind == "table":
            headers, rows = block[1], block[2]
            data = [[Paragraph(f"<b>{_pdf_text(c)}</b>", small) for c in headers]]
            data += [[Paragraph(_pdf_text(str(c)), small) for c in row] for row in rows]
            if not rows:
                data.append([Paragraph("No records.", small)] + [""] * (len(headers) - 1))
            t = Table(data, repeatRows=1, colWidths=[width / len(headers)] * len(headers))
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf6")),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9d1df")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(t)
            story.append(Spacer(1, 6))
    doc.build(story)
    return buf.getvalue()


def render_docx(report: Report) -> bytes:
    import docx
    from docx.shared import Pt, RGBColor

    d = docx.Document()
    style = d.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    d.core_properties.title = report.title
    d.core_properties.author = "TenderPilot AI"
    d.add_heading(report.title, level=0)
    sub = d.add_paragraph(report.subtitle)
    sub.runs[0].font.color.rgb = RGBColor(0x5B, 0x64, 0x78)
    for block in report.blocks:
        kind = block[0]
        if kind == "h":
            d.add_heading(block[1], level=2)
        elif kind == "p":
            for para in block[1].split("\n"):
                d.add_paragraph(para)
        elif kind == "notice":
            p = d.add_paragraph()
            run = p.add_run(block[1])
            run.bold = True
            run.font.color.rgb = RGBColor(0x8A, 0x5A, 0x00)
        elif kind == "bullets":
            for item in block[1]:
                d.add_paragraph(item, style="List Bullet")
        elif kind == "kv":
            t = d.add_table(rows=0, cols=2)
            t.style = "Table Grid"
            for k, v in block[1]:
                cells = t.add_row().cells
                cells[0].text = k
                cells[1].text = v or "-"
                for r in cells[0].paragraphs[0].runs:
                    r.bold = True
        elif kind == "table":
            headers, rows = block[1], block[2]
            t = d.add_table(rows=1, cols=len(headers))
            t.style = "Table Grid"
            for i, hdr in enumerate(headers):
                t.rows[0].cells[i].text = hdr
                for r in t.rows[0].cells[i].paragraphs[0].runs:
                    r.bold = True
            for row in rows:
                cells = t.add_row().cells
                for i, c in enumerate(row):
                    cells[i].text = str(c)
            d.add_paragraph()
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _safe_csv_cell(value: object) -> str:
    """Prevent CSV/formula injection when opened in spreadsheet software."""
    s = "" if value is None else str(value)
    if s[:1] in ("=", "+", "-", "@", "\t", "\r"):
        s = "'" + s
    return s


def render_csv(headers: list[str], rows: Sequence[Sequence[object]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for row in rows:
        w.writerow([_safe_csv_cell(c) for c in row])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM so Excel detects UTF-8
