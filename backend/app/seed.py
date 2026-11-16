"""Explicit demo-data seed command.

    python -m app.seed --email you@example.com [--password ...]

Creates a separate demo organisation whose records are all prefixed "[DEMO]". It never touches
existing users or organisations, and refuses to run if the email is already registered.
"""

from __future__ import annotations

import argparse
import secrets
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password, validate_password_strength
from app.db.session import SessionLocal
from app.models import CompanyProfile, Document, Membership, Organization, Task, Tender, User
from app.services import storage
from app.services.access import log_activity
from app.services.extraction import extract, validate_upload

SAMPLE_TENDER = """[DEMO] Invitation to Tender - Managed IT Support Services
Contracting Authority: Northbridge Borough Council (fictional demo buyer)
Tender Reference: NBC-IT-2027-014

1. Introduction
The Council is seeking a supplier to provide managed IT support services for 450 users across 6 sites.
The contract duration is 36 months with an option to extend by 12 months.
The estimated contract value is EUR 1,200,000 excluding VAT.

2. Timetable
Clarification questions must be submitted no later than 20 January 2027.
The deadline for receipt of tenders is 3 February 2027 at 12:00.
Contract award is expected on 1 March 2027.

3. Eligibility and Mandatory Requirements
Bidders must have a minimum annual turnover of EUR 2,000,000 in each of the last two financial years.
Bidders must hold a valid ISO 27001 certification at the time of submission.
Bidders shall hold Cyber Essentials Plus certification.
Bidders must provide evidence of at least three contracts of similar scope delivered in the last five years.
Bidders must provide a copy of their public liability insurance certificate of at least EUR 5,000,000.

4. Technical Requirements
The service desk must be available from 08:00 to 18:00 on working days.
The supplier shall resolve priority 1 incidents within 4 hours.
The supplier must provide a named service delivery manager.
All data must be hosted within the European Economic Area.
The supplier should provide monthly service performance reports.

5. Commercial Terms
Pricing must be submitted as a fixed monthly fee using the pricing schedule.
Service credits of up to 10% of the monthly fee apply for missed service levels.
Payment will be made within 30 days of a valid invoice.

6. Evaluation Criteria
Quality will be weighted at 60% and price at 40%.
Within quality, technical approach is worth 30%, service management 20% and social value 10%.

7. Submission Instructions
Tenders must be submitted via the e-procurement portal in PDF format.
Responses must not exceed 20 pages excluding appendices.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed clearly-labelled demo data.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", default=None, help="If omitted, a random password is generated and printed once.")
    args = parser.parse_args()
    password = args.password or secrets.token_urlsafe(12) + "1a"
    if (err := validate_password_strength(password)) is not None:
        print(f"Password rejected: {err}")
        return 1

    db = SessionLocal()
    try:
        email = args.email.lower()
        if db.scalar(select(User.id).where(User.email == email)):
            print("That email is already registered - choose another email for the demo account.")
            return 1
        org = Organization(name="[DEMO] Example Consulting Ltd")
        db.add(org)
        db.flush()
        user = User(email=email, full_name="Demo User", password_hash=hash_password(password))
        db.add(user)
        db.flush()
        db.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))
        db.add(
            CompanyProfile(
                organization_id=org.id,
                company_name="[DEMO] Example Consulting Ltd",
                overview="[DEMO] Fictional company used to demonstrate TenderPilot AI. Replace with your verified company information.",
            )
        )
        now = datetime.now(UTC)
        samples = [
            (
                "[DEMO] Managed IT Support Services",
                "Northbridge Borough Council (fictional)",
                "NBC-IT-2027-014",
                "under_review",
                "high",
                21,
                Decimal("1200000"),
            ),
            ("[DEMO] Cloud Migration Framework", "Fictional Health Trust", "FHT-CM-0099", "in_preparation", "critical", 9, Decimal("750000")),
            ("[DEMO] Website Redesign RFQ", "Fictional Museum", "FM-RFQ-12", "draft", "medium", 40, None),
            ("[DEMO] Data Platform RFP", "Fictional Water Utility", "FWU-2026-77", "won", "medium", -30, Decimal("420000")),
            ("[DEMO] Training Services", "Fictional University", "FU-TS-5", "lost", "low", -60, Decimal("90000")),
        ]
        first = None
        for title, buyer, ref, status, prio, days, value in samples:
            t = Tender(
                organization_id=org.id,
                created_by_id=user.id,
                title=title,
                buyer=buyer,
                reference=ref,
                description="Demo record created by the seed command.",
                tender_type="rfp",
                status=status,
                priority=prio,
                submission_deadline=now + timedelta(days=days),
                estimated_value=value,
                currency="EUR",
            )
            db.add(t)
            db.flush()
            log_activity(db, org.id, user.id, "tender.created", f"Tender '{title}' created (seed)", t.id)
            first = first or t
        assert first is not None
        data = SAMPLE_TENDER.encode()
        info = validate_upload("demo-invitation-to-tender.txt", "text/plain", data, 10_000_000)
        key = storage.new_storage_key("txt")
        storage.save(db, key, data)
        result = extract("txt", data)
        db.add(
            Document(
                tender_id=first.id,
                organization_id=org.id,
                uploaded_by_id=user.id,
                original_filename=info.original_filename,
                storage_key=key,
                content_type=info.content_type,
                file_ext="txt",
                size_bytes=info.size,
                sha256=info.sha256,
                status=result.status,
                status_message=result.message,
                pages=result.pages,
                page_count=None,
                char_count=result.char_count,
                processed_at=now,
            )
        )
        db.add(
            Task(
                organization_id=org.id,
                tender_id=first.id,
                created_by_id=user.id,
                assignee_id=user.id,
                title="[DEMO] Confirm ISO 27001 certificate is current",
                priority="high",
                due_date=(now + timedelta(days=5)).date(),
            )
        )
        db.commit()
    finally:
        db.close()
    print(f"Demo account created: {args.email}")
    if not args.password:
        print(f"Generated password (shown once): {password}")
    print("All demo records are prefixed with [DEMO].")
    return 0


if __name__ == "__main__":
    sys.exit(main())
