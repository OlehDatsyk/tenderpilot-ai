from __future__ import annotations

from tests.conftest import make_tender


def test_tender_crud(alice):
    t = make_tender(alice, estimated_value="125000.50", currency="gbp", submission_deadline="2027-03-01T12:00:00Z", tender_type="rfp")
    assert t["currency"] == "GBP" and t["status"] == "draft"
    detail = alice.get(f"/api/v1/tenders/{t['id']}").json()
    assert detail["document_count"] == 0 and detail["compliance"]["total"] == 0
    assert detail["created_by_name"] == "Test User"

    r = alice.patch(f"/api/v1/tenders/{t['id']}", json={"status": "under_review", "notes": "Internal", "priority": "high"})
    assert r.status_code == 200
    assert r.json()["status"] == "under_review" and r.json()["notes"] == "Internal"

    acts = alice.get(f"/api/v1/activity?tender_id={t['id']}").json()
    assert any(a["action"] == "tender.status_changed" for a in acts)

    assert alice.delete(f"/api/v1/tenders/{t['id']}").status_code == 204
    assert alice.get(f"/api/v1/tenders/{t['id']}").status_code == 404


def test_tender_validation(alice):
    assert alice.post("/api/v1/tenders", json={"title": "  "}).status_code == 422
    assert alice.post("/api/v1/tenders", json={"title": "x", "status": "bogus"}).status_code == 422
    assert alice.post("/api/v1/tenders", json={"title": "x", "currency": "E1"}).status_code == 422
    assert alice.post("/api/v1/tenders", json={"title": "x", "estimated_value": -5}).status_code == 422
    assert alice.get("/api/v1/tenders/not-a-uuid").status_code == 422


def test_search_filter_sort_paginate(alice):
    make_tender(alice, title="Cloud hosting", buyer="Health Trust", status="draft", priority="low")
    make_tender(alice, title="Website redesign", buyer="Museum", status="under_review", priority="critical", submission_deadline="2027-01-01T00:00:00Z")
    make_tender(alice, title="Cloud backup", buyer="University", status="submitted", priority="medium", submission_deadline="2026-12-01T00:00:00Z")

    r = alice.get("/api/v1/tenders", params={"q": "cloud"}).json()
    assert r["total"] == 2
    r = alice.get("/api/v1/tenders", params={"q": "museum"}).json()
    assert [t["title"] for t in r["items"]] == ["Website redesign"]
    r = alice.get("/api/v1/tenders", params=[("status", "draft"), ("status", "submitted")]).json()
    assert r["total"] == 2
    r = alice.get("/api/v1/tenders", params={"sort": "priority", "order": "desc"}).json()
    assert r["items"][0]["priority"] == "critical"
    r = alice.get("/api/v1/tenders", params={"sort": "submission_deadline", "order": "asc"}).json()
    assert r["items"][0]["title"] == "Cloud backup" and r["items"][-1]["submission_deadline"] is None
    r = alice.get("/api/v1/tenders", params={"page_size": 2, "page": 2}).json()
    assert r["total"] == 3 and len(r["items"]) == 1


def test_archive_and_restore(alice):
    t = make_tender(alice)
    alice.patch(f"/api/v1/tenders/{t['id']}", json={"is_archived": True})
    assert alice.get("/api/v1/tenders").json()["total"] == 0
    assert alice.get("/api/v1/tenders", params={"archived": True}).json()["total"] == 1
    alice.patch(f"/api/v1/tenders/{t['id']}", json={"is_archived": False})
    assert alice.get("/api/v1/tenders").json()["total"] == 1


def test_dashboard_reflects_real_records(alice):
    empty = alice.get("/api/v1/dashboard").json()
    assert empty["stats"]["total_tenders"] == 0 and empty["stats"]["win_rate"] is None
    make_tender(alice, status="under_review", submission_deadline="2099-01-01T00:00:00Z")
    make_tender(alice, status="won")
    make_tender(alice, status="lost")
    make_tender(alice, status="in_preparation")
    d = alice.get("/api/v1/dashboard").json()
    assert d["stats"]["total_tenders"] == 4
    assert d["stats"]["active_tenders"] == 2
    assert d["stats"]["awaiting_review"] == 1
    assert d["stats"]["won"] == 1 and d["stats"]["lost"] == 1 and d["stats"]["win_rate"] == 50.0
    assert sum(p["count"] for p in d["pipeline"]) == 4
    assert len(d["recent_activity"]) >= 4


def test_analytics(alice):
    make_tender(alice, status="won", estimated_value=1000)
    make_tender(alice, status="draft")
    a = alice.get("/api/v1/analytics").json()
    assert a["win_loss"]["won"] == 1 and a["win_loss"]["win_rate"] == 100.0
    assert sum(m["created"] for m in a["monthly"]) == 2
    assert {"status": "won", "currency": "EUR", "value": 1000.0} in a["pipeline_value"]
    assert a["compliance"]["percent_complete"] is None
