from __future__ import annotations

import io
from datetime import date, timedelta

import docx
from pypdf import PdfReader

from app.services.exports import render_csv
from tests.conftest import make_tender, set_provider, upload_txt


def _reqs(acct, tid, items):
    out = []
    for desc, mandatory, category in items:
        r = acct.post(f"/api/v1/tenders/{tid}/requirements", json={"description": desc, "is_mandatory": mandatory, "category": category})
        assert r.status_code == 201
        out.append(r.json())
    return out


def test_compliance_percentages_and_filters(alice):
    t = make_tender(alice)
    r1, r2, r3, r4 = _reqs(
        alice,
        t["id"],
        [
            ("Hold ISO 27001", True, "certification"),
            ("Provide CVs", True, "supporting_document"),
            ("Offer training", False, "technical"),
            ("Fixed price", False, "commercial"),
        ],
    )
    assert r1["origin"] == "manual" and r1["source_verified"] is False
    summary = alice.get(f"/api/v1/tenders/{t['id']}/compliance").json()
    assert summary["total"] == 4 and summary["percent_complete"] == 0.0

    alice.patch(f"/api/v1/requirements/{r1['id']}", json={"response_status": "compliant", "evidence": "Cert 123"})
    alice.patch(f"/api/v1/requirements/{r3['id']}", json={"response_status": "non_compliant"})
    alice.patch(f"/api/v1/requirements/{r4['id']}", json={"response_status": "in_progress"})
    summary = alice.get(f"/api/v1/tenders/{t['id']}/compliance").json()
    assert summary["addressed"] == 2 and summary["percent_complete"] == 50.0
    assert summary["mandatory_percent_complete"] == 50.0
    assert summary["by_status"]["in_progress"] == 1

    assert len(alice.get(f"/api/v1/tenders/{t['id']}/requirements", params={"mandatory": True}).json()) == 2
    assert len(alice.get(f"/api/v1/tenders/{t['id']}/requirements", params={"status": "compliant"}).json()) == 1
    assert len(alice.get(f"/api/v1/tenders/{t['id']}/requirements", params={"category": "commercial"}).json()) == 1
    assert len(alice.get(f"/api/v1/tenders/{t['id']}/requirements", params={"q": "cert 123"}).json()) == 1
    assert alice.patch(f"/api/v1/requirements/{r2['id']}", json={"response_status": "done"}).status_code == 422

    me = alice.me["id"]
    r = alice.patch(f"/api/v1/requirements/{r2['id']}", json={"assignee_id": me}).json()
    assert r["assignee_name"] == "Test User"
    r = alice.patch(f"/api/v1/requirements/{r2['id']}", json={"clear_assignee": True}).json()
    assert r["assignee_id"] is None

    listed = alice.get("/api/v1/tenders").json()["items"][0]
    assert listed["requirement_count"] == 4 and listed["compliance_percent"] == 50.0

    assert alice.delete(f"/api/v1/requirements/{r4['id']}").status_code == 204
    assert alice.get(f"/api/v1/tenders/{t['id']}/compliance").json()["total"] == 3


def test_tasks_and_comments(alice):
    t = make_tender(alice)
    me = alice.me["id"]
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    task = alice.post("/api/v1/tasks", json={"title": "Collect CVs", "tender_id": t["id"], "assignee_id": me, "due_date": yesterday, "priority": "high"}).json()
    assert task["is_overdue"] is True and task["tender_title"] == "Managed IT services" and task["assignee_name"] == "Test User"
    alice.post("/api/v1/tasks", json={"title": "Org-level task"})
    assert len(alice.get("/api/v1/tasks").json()) == 2
    assert len(alice.get("/api/v1/tasks", params={"tender_id": t["id"]}).json()) == 1
    assert len(alice.get("/api/v1/tasks", params={"overdue": True}).json()) == 1
    assert len(alice.get("/api/v1/tasks", params={"assignee": "me"}).json()) == 1

    c = alice.post(f"/api/v1/tasks/{task['id']}/comments", json={"body": "Waiting on HR"}).json()
    detail = alice.get(f"/api/v1/tasks/{task['id']}").json()
    assert detail["comments"][0]["body"] == "Waiting on HR" and detail["comment_count"] == 1

    done = alice.patch(f"/api/v1/tasks/{task['id']}", json={"status": "done"}).json()
    assert done["completed_at"] is not None and done["is_overdue"] is False
    cleared = alice.patch(f"/api/v1/tasks/{task['id']}", json={"clear_due_date": True, "clear_assignee": True}).json()
    assert cleared["due_date"] is None and cleared["assignee_id"] is None
    assert alice.delete(f"/api/v1/tasks/{task['id']}/comments/{c['id']}").status_code == 204
    assert alice.delete(f"/api/v1/tasks/{task['id']}").status_code == 204
    assert alice.post("/api/v1/tasks", json={"title": ""}).status_code == 422


def test_exports_contain_project_data_and_labels(alice):
    set_provider(alice, "demo")
    t = make_tender(alice, title="Export Tender")
    upload_txt(alice, t["id"])
    alice.post(f"/api/v1/tenders/{t['id']}/analysis")
    alice.post(f"/api/v1/tenders/{t['id']}/bid-assessments")
    prop = alice.post(f"/api/v1/tenders/{t['id']}/proposals", json={"title": "Proposal X", "use_ai_outline": True}).json()

    pdf = alice.get(f"/api/v1/tenders/{t['id']}/exports/analysis?format=pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Tender Analysis Report" in text and "DEMO MODE" in text and "ISO 27001" in text

    d = alice.get(f"/api/v1/tenders/{t['id']}/exports/bid?format=docx")
    assert d.status_code == 200
    body = "\n".join(p.text for p in docx.Document(io.BytesIO(d.content)).paragraphs)
    assert "Bid / No-Bid Report" in body and "not a guarantee" in body

    csv_r = alice.get(f"/api/v1/tenders/{t['id']}/exports/compliance?format=csv")
    assert csv_r.status_code == 200 and "Requirement" in csv_r.text and "Demo heuristic" in csv_r.text

    for kind in ("summary", "compliance"):
        for fmt in ("pdf", "docx"):
            assert alice.get(f"/api/v1/tenders/{t['id']}/exports/{kind}?format={fmt}").status_code == 200, (kind, fmt)

    p = alice.get(f"/api/v1/tenders/{t['id']}/exports/proposal?format=docx&proposal_id={prop['id']}")
    assert p.status_code == 200
    body = "\n".join(x.text for x in docx.Document(io.BytesIO(p.content)).paragraphs)
    assert "Proposal X" in body and "DRAFT" in body

    assert alice.get(f"/api/v1/tenders/{t['id']}/exports/summary?format=csv").status_code == 422
    assert alice.get(f"/api/v1/tenders/{t['id']}/exports/proposal?format=pdf").status_code == 422


def test_export_404_when_nothing_to_export(alice):
    t = make_tender(alice)
    assert alice.get(f"/api/v1/tenders/{t['id']}/exports/analysis?format=pdf").status_code == 404
    assert alice.get(f"/api/v1/tenders/{t['id']}/exports/bid?format=pdf").status_code == 404


def test_csv_formula_injection_is_neutralised():
    out = render_csv(["a"], [['=HYPERLINK("http://x")'], ["+1"], ["normal"]]).decode("utf-8-sig")
    assert "'=HYPERLINK" in out and "'+1" in out and "\nnormal" in out


def test_company_profile(alice):
    p = alice.get("/api/v1/organization/company-profile").json()
    assert p["completeness"] == 0
    r = alice.put("/api/v1/organization/company-profile", json={"company_name": "Acme", "overview": "We do IT.", "certifications": "ISO 9001"})
    assert r.status_code == 200 and r.json()["completeness"] == 33
