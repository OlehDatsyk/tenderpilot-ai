"""Document upload, processing status, extracted text, download, re-processing and deletion."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select

from app.api.deps import DB, Ctx
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Document
from app.schemas.domain import DocumentOut, DocumentTextOut
from app.services import storage
from app.services.access import get_document, get_tender, log_activity
from app.services.extraction import UploadValidationError, extract, validate_upload

router = APIRouter(tags=["documents"])
logger = logging.getLogger("tenderpilot.documents")


def process_document(document_id: uuid.UUID) -> None:
    """Background job: extract text from a stored document (own DB session)."""
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.status, doc.status_message = "processing", "Extracting text…"
        db.commit()
        try:
            data = storage.load(db, doc.storage_key)
            result = extract(doc.file_ext, data)
            doc.status, doc.status_message = result.status, result.message
            doc.pages, doc.page_count, doc.char_count = result.pages, result.page_count, result.char_count
        except storage.StorageError as exc:
            doc.status, doc.status_message = "failed", str(exc)
        except Exception:  # noqa: BLE001 - parser libraries can raise anything on hostile input
            logger.exception("Text extraction failed for document %s", document_id)
            doc.status, doc.status_message = "failed", "Text extraction failed for this file."
        doc.processed_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


@router.get("/tenders/{tender_id}/documents", response_model=list[DocumentOut])
def list_documents(tender_id: uuid.UUID, ctx: Ctx, db: DB) -> list[Document]:
    get_tender(db, ctx.org_id, tender_id)
    return list(
        db.scalars(select(Document).where(Document.tender_id == tender_id, Document.organization_id == ctx.org_id).order_by(Document.created_at.desc()))
    )


@router.post("/tenders/{tender_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(tender_id: uuid.UUID, ctx: Ctx, db: DB, background: BackgroundTasks, file: UploadFile = File(...)) -> Document:
    tender = get_tender(db, ctx.org_id, tender_id)
    max_bytes = get_settings().max_upload_bytes
    data = file.file.read(max_bytes + 1)
    try:
        info = validate_upload(file.filename or "", file.content_type, data, max_bytes)
    except UploadValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    duplicate = db.scalar(select(Document.id).where(Document.tender_id == tender.id, Document.sha256 == info.sha256))
    if duplicate is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This file has already been uploaded to this tender.")
    key = storage.new_storage_key(info.ext)
    try:
        storage.save(db, key, data)
    except storage.StorageError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    doc = Document(
        tender_id=tender.id,
        organization_id=ctx.org_id,
        uploaded_by_id=ctx.user.id,
        original_filename=info.original_filename,
        storage_key=key,
        content_type=info.content_type,
        file_ext=info.ext,
        size_bytes=info.size,
        sha256=info.sha256,
        status="pending",
        status_message="Queued for text extraction.",
    )
    db.add(doc)
    log_activity(db, ctx.org_id, ctx.user.id, "document.uploaded", f"Document '{info.original_filename}' uploaded", tender.id)
    db.commit()
    background.add_task(process_document, doc.id)
    return doc


@router.get("/tenders/{tender_id}/documents/{document_id}", response_model=DocumentOut)
def get_document_meta(tender_id: uuid.UUID, document_id: uuid.UUID, ctx: Ctx, db: DB) -> Document:
    return get_document(db, ctx.org_id, tender_id, document_id)


@router.get("/tenders/{tender_id}/documents/{document_id}/text", response_model=DocumentTextOut)
def get_document_text(tender_id: uuid.UUID, document_id: uuid.UUID, ctx: Ctx, db: DB) -> DocumentTextOut:
    doc = get_document(db, ctx.org_id, tender_id, document_id)
    return DocumentTextOut(id=doc.id, original_filename=doc.original_filename, status=doc.status, pages=doc.pages or [])


@router.get("/tenders/{tender_id}/documents/{document_id}/download")
def download_document(tender_id: uuid.UUID, document_id: uuid.UUID, ctx: Ctx, db: DB) -> Response:
    doc = get_document(db, ctx.org_id, tender_id, document_id)
    try:
        data = storage.load(db, doc.storage_key)
    except storage.StorageError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return Response(
        content=data,
        media_type=doc.content_type,
        headers={
            # Always download, never render inline - uploaded files are untrusted.
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc.original_filename)}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/tenders/{tender_id}/documents/{document_id}/reprocess", response_model=DocumentOut)
def reprocess_document(tender_id: uuid.UUID, document_id: uuid.UUID, ctx: Ctx, db: DB, background: BackgroundTasks) -> Document:
    doc = get_document(db, ctx.org_id, tender_id, document_id)
    if doc.status == "processing":
        raise HTTPException(status.HTTP_409_CONFLICT, "The document is already being processed.")
    doc.status, doc.status_message = "pending", "Queued for text extraction."
    db.commit()
    background.add_task(process_document, doc.id)
    return doc


@router.delete("/tenders/{tender_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(tender_id: uuid.UUID, document_id: uuid.UUID, ctx: Ctx, db: DB) -> Response:
    doc = get_document(db, ctx.org_id, tender_id, document_id)
    storage.remove(db, doc.storage_key)
    name = doc.original_filename
    db.delete(doc)
    log_activity(db, ctx.org_id, ctx.user.id, "document.deleted", f"Document '{name}' deleted", tender_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
