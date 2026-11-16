"""Organisation-level data isolation: guessing or swapping IDs must never expose another org's data."""

from __future__ import annotations

from tests.conftest import make_tender, set_provider, upload_txt


def _setup_alice(alice):
    set_provider(alice, "demo")
    t = make_tender(alice, title="Alice confidential bid")
    doc = upload_txt(alice, t["id"])
    run = alice.post(f"/api/v1/tenders/{t['id']}/analysis").json()
    reqs = alice.get(f"/api/v1/tenders/{t['id']}/requirements").json()
    assert reqs, "demo analysis should create requirements"
    bid = alice.post(f"/api/v1/tenders/{t['id']}/bid-assessments").json()
    prop = alice.post(f"/api/v1/tenders/{t['id']}/proposals", json={"title": "Draft", "use_ai_outline": True}).json()
    task = alice.post("/api/v1/tasks", json={"title": "Alice task", "tender_id": t["id"]}).json()
    alice.post(f"/api/v1/tenders/{t['id']}/assistant/messages", json={"question": "ISO certification?"})
    return t, doc, run, reqs[0], bid, prop, task


def test_other_org_cannot_read_or_modify_anything(alice, bob):
    t, doc, run, req, bid, prop, task = _setup_alice(alice)
    tid = t["id"]
    reads = [
        f"/api/v1/tenders/{tid}",
        f"/api/v1/tenders/{tid}/documents",
        f"/api/v1/tenders/{tid}/documents/{doc['id']}",
        f"/api/v1/tenders/{tid}/documents/{doc['id']}/text",
        f"/api/v1/tenders/{tid}/documents/{doc['id']}/download",
        f"/api/v1/tenders/{tid}/requirements",
        f"/api/v1/tenders/{tid}/compliance",
        f"/api/v1/tenders/{tid}/analysis/runs",
        f"/api/v1/tenders/{tid}/analysis/latest",
        f"/api/v1/analysis/runs/{run['id']}",
        f"/api/v1/tenders/{tid}/bid-assessments",
        f"/api/v1/tenders/{tid}/proposals",
        f"/api/v1/proposals/{prop['id']}",
        f"/api/v1/proposals/{prop['id']}/coverage",
        f"/api/v1/tenders/{tid}/assistant/messages",
        f"/api/v1/tasks/{task['id']}",
        f"/api/v1/tenders/{tid}/exports/summary?format=pdf",
        f"/api/v1/tenders/{tid}/exports/compliance?format=csv",
        f"/api/v1/tasks?tender_id={tid}",
    ]
    for url in reads:
        r = bob.get(url)
        assert r.status_code == 404, f"{url} -> {r.status_code}"

    section_id = prop["sections"][0]["id"]
    writes = [
        ("patch", f"/api/v1/tenders/{tid}", {"title": "pwned"}),
        ("delete", f"/api/v1/tenders/{tid}", None),
        ("post", f"/api/v1/tenders/{tid}/analysis", None),
        ("post", f"/api/v1/tenders/{tid}/requirements", {"description": "injected requirement"}),
        ("patch", f"/api/v1/requirements/{req['id']}", {"response_status": "compliant"}),
        ("delete", f"/api/v1/requirements/{req['id']}", None),
        ("post", f"/api/v1/bid-assessments/{bid['id']}/decision", {"final_decision": "no_bid", "final_reasoning": "pwned"}),
        ("patch", f"/api/v1/proposals/{prop['id']}", {"title": "pwned"}),
        ("patch", f"/api/v1/proposals/{prop['id']}/sections/{section_id}", {"content": "pwned"}),
        ("post", f"/api/v1/proposals/{prop['id']}/sections/{section_id}/generate", {"mode": "draft"}),
        ("delete", f"/api/v1/tenders/{tid}/documents/{doc['id']}", None),
        ("post", f"/api/v1/tenders/{tid}/documents/{doc['id']}/reprocess", None),
        ("patch", f"/api/v1/tasks/{task['id']}", {"title": "pwned"}),
        ("post", f"/api/v1/tasks/{task['id']}/comments", {"body": "hi"}),
        ("post", f"/api/v1/tenders/{tid}/assistant/messages", {"question": "What is in this tender?"}),
    ]
    for method, url, body in writes:
        kw = {"json": body} if body is not None else {}
        r = getattr(bob, method)(url, **kw)
        assert r.status_code == 404, f"{method} {url} -> {r.status_code}"

    # Bob cannot attach his task to Alice's tender or assign Alice.
    assert bob.post("/api/v1/tasks", json={"title": "x", "tender_id": tid}).status_code == 404
    assert bob.post("/api/v1/tasks", json={"title": "x", "assignee_id": alice.me["id"]}).status_code == 422

    # Alice's data is untouched and Bob's listings are empty.
    assert alice.get(f"/api/v1/tenders/{tid}").json()["title"] == "Alice confidential bid"
    assert bob.get("/api/v1/tenders").json()["total"] == 0
    assert bob.get("/api/v1/tasks").json() == []
    assert bob.get("/api/v1/activity").json() == [] or all(a["tender_id"] != tid for a in bob.get("/api/v1/activity").json())
    assert bob.get("/api/v1/dashboard").json()["stats"]["total_tenders"] == 0


def test_requirement_cannot_be_assigned_to_other_org_user(alice, bob):
    set_provider(alice, "demo")
    t = make_tender(alice)
    req = alice.post(f"/api/v1/tenders/{t['id']}/requirements", json={"description": "Provide CVs"}).json()
    r = alice.patch(f"/api/v1/requirements/{req['id']}", json={"assignee_id": bob.me["id"]})
    assert r.status_code == 422


def test_assistant_history_is_private_per_user(client, alice):
    from tests.conftest import register

    set_provider(alice, "demo")
    token = alice.post("/api/v1/organization/invitations", json={"email": "colleague@example.com"}).json()["token"]
    colleague = register(client, "colleague@example.com", invitation_token=token)
    t = make_tender(alice)
    upload_txt(alice, t["id"])
    alice.post(f"/api/v1/tenders/{t['id']}/assistant/messages", json={"question": "Tell me about ISO certification"})
    assert len(alice.get(f"/api/v1/tenders/{t['id']}/assistant/messages").json()) == 2
    assert colleague.get(f"/api/v1/tenders/{t['id']}/assistant/messages").json() == []
