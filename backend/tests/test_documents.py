from __future__ import annotations

import io

import docx
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.services.extraction import UploadValidationError, extract, safe_filename, validate_upload
from tests.conftest import make_tender, upload_txt


def make_pdf(pages: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for text in pages:
        y = 800
        for line in text.splitlines():
            c.drawString(50, y, line)
            y -= 14
        c.showPage()
    c.save()
    return buf.getvalue()


def make_docx(paragraphs: list[str]) -> bytes:
    d = docx.Document()
    for p in paragraphs:
        d.add_paragraph(p)
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = "Criterion"
    t.rows[0].cells[1].text = "Weight 60%"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_pdf_extraction_keeps_page_numbers():
    data = make_pdf(["Page one introduction text for the tender document.", "Bidders must hold ISO 9001 certification."])
    res = extract("pdf", data)
    assert res.status == "processed" and res.page_count == 2
    assert res.pages[1]["page"] == 2 and "ISO 9001" in res.pages[1]["text"]


def test_scanned_pdf_reports_ocr_unavailable():
    res = extract("pdf", make_pdf(["", ""]))
    assert res.status == "needs_ocr"
    assert "OCR is not configured" in res.message
    assert res.char_count == 0


def test_docx_extraction_includes_tables_and_no_fake_pages():
    res = extract("docx", make_docx(["The supplier shall provide support.", "Second paragraph."]))
    assert res.status == "processed"
    assert all(p["page"] is None for p in res.pages)
    assert "Weight 60%" in res.pages[0]["text"]


def test_validation_rejects_bad_files():
    cases = [
        ("evil.exe", "application/octet-stream", b"MZ..."),
        ("doc.pdf", "application/pdf", b"not really a pdf"),
        ("doc.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04garbage"),
        ("notes.txt", "text/plain", b"\x00\x01\x02binary"),
        ("doc.pdf", "text/html", make_pdf(["x"])),
        ("empty.txt", "text/plain", b""),
    ]
    for name, ctype, data in cases:
        try:
            validate_upload(name, ctype, data, 1_000_000)
        except UploadValidationError:
            continue
        raise AssertionError(f"{name} should have been rejected")
    try:
        validate_upload("big.txt", "text/plain", b"a" * 2000, 1000)
        raise AssertionError("size limit not enforced")
    except UploadValidationError as exc:
        assert "maximum upload size" in str(exc)


def test_safe_filename_blocks_traversal():
    assert safe_filename("../../etc/passwd.txt") == "passwd.txt"
    assert safe_filename("..\\..\\windows\\system32\\x.pdf") == "x.pdf"
    assert "/" not in safe_filename("a/b/<script>.txt")
    assert safe_filename("") == "document"


def test_upload_lifecycle(alice):
    t = make_tender(alice)
    doc = upload_txt(alice, t["id"], name="../../../evil name.txt")
    assert doc["original_filename"] == "evil name.txt"
    # TestClient runs background tasks before returning, so processing has completed.
    meta = alice.get(f"/api/v1/tenders/{t['id']}/documents/{doc['id']}").json()
    assert meta["status"] == "processed" and meta["char_count"] > 50
    text = alice.get(f"/api/v1/tenders/{t['id']}/documents/{doc['id']}/text").json()
    assert "ISO 27001" in text["pages"][0]["text"]

    dl = alice.get(f"/api/v1/tenders/{t['id']}/documents/{doc['id']}/download")
    assert dl.status_code == 200 and dl.headers["content-disposition"].startswith("attachment;")
    assert dl.content.startswith(b"Invitation to Tender")

    # duplicate upload is rejected
    r = alice.post(f"/api/v1/tenders/{t['id']}/documents", files={"file": ("copy.txt", dl.content, "text/plain")})
    assert r.status_code == 409

    assert alice.post(f"/api/v1/tenders/{t['id']}/documents/{doc['id']}/reprocess").json()["id"] == doc["id"]
    assert alice.get(f"/api/v1/tenders/{t['id']}/documents/{doc['id']}").json()["status"] == "processed"

    assert alice.delete(f"/api/v1/tenders/{t['id']}/documents/{doc['id']}").status_code == 204
    assert alice.get(f"/api/v1/tenders/{t['id']}/documents").json() == []


def test_upload_pdf_and_docx_via_api(alice):
    t = make_tender(alice)
    r = alice.post(f"/api/v1/tenders/{t['id']}/documents", files={"file": ("spec.pdf", make_pdf(["Bidders must comply with GDPR."]), "application/pdf")})
    assert r.status_code == 201
    r2 = alice.post(
        f"/api/v1/tenders/{t['id']}/documents",
        files={
            "file": ("spec.docx", make_docx(["The supplier shall provide CVs."]), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        },
    )
    assert r2.status_code == 201
    docs = alice.get(f"/api/v1/tenders/{t['id']}/documents").json()
    assert {d["status"] for d in docs} == {"processed"}


def test_upload_rejections_via_api(alice):
    t = make_tender(alice)
    r = alice.post(f"/api/v1/tenders/{t['id']}/documents", files={"file": ("x.html", b"<script>alert(1)</script>", "text/html")})
    assert r.status_code == 422
    big = b"a" * (2 * 1024 * 1024 + 10)  # MAX_UPLOAD_MB=2 in tests
    r = alice.post(f"/api/v1/tenders/{t['id']}/documents", files={"file": ("big.txt", big, "text/plain")})
    assert r.status_code == 422 and "maximum upload size" in r.json()["detail"]
