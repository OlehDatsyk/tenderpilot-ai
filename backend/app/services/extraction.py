"""Upload validation and text extraction for PDF, DOCX and TXT files.

Uploaded content is treated as untrusted data: it is parsed with pure-Python libraries and never
executed. Scanned PDFs without a text layer are reported as ``needs_ocr`` - no text is invented.
"""

from __future__ import annotations

import hashlib
import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePath

from app.models.enums import ALLOWED_EXTENSIONS

MAX_PAGES = 2000
SECTION_CHARS = 3000
MIN_CHARS_PER_PAGE_FOR_TEXT_LAYER = 20


class UploadValidationError(ValueError):
    pass


@dataclass
class ValidatedUpload:
    original_filename: str
    ext: str
    content_type: str
    size: int
    sha256: str


@dataclass
class ExtractionResult:
    status: str  # processed | needs_ocr | failed
    message: str
    pages: list[dict] = field(default_factory=list)
    page_count: int | None = None

    @property
    def char_count(self) -> int:
        return sum(len(p["text"]) for p in self.pages)


def safe_filename(name: str) -> str:
    """Display-safe filename: basename only, no control chars, limited charset and length."""
    name = PurePath(name.replace("\\", "/")).name
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[^\w.\- ()]+", "_", name).strip(" .")
    if not name:
        name = "document"
    stem, dot, ext = name.rpartition(".")
    if dot and len(name) > 200:
        name = stem[: 200 - len(ext) - 1] + "." + ext
    return name[:200]


def _sniff(ext: str, data: bytes) -> bool:
    if ext == "pdf":
        return data[:1024].lstrip().startswith(b"%PDF-")
    if ext == "docx":
        if not data.startswith(b"PK\x03\x04"):
            return False
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
                if "word/document.xml" not in names:
                    return False
                # zip-bomb guard
                total = sum(i.file_size for i in zf.infolist())
                return total < 200 * 1024 * 1024
        except zipfile.BadZipFile:
            return False
    if ext == "txt":
        if b"\x00" in data[:8192]:
            return False
        try:
            data.decode("utf-8")
            return True
        except UnicodeDecodeError:
            try:
                data.decode("cp1252")
                return True
            except UnicodeDecodeError:
                return False
    return False


def validate_upload(filename: str, declared_content_type: str | None, data: bytes, max_bytes: int) -> ValidatedUpload:
    clean = safe_filename(filename or "")
    ext = clean.rsplit(".", 1)[-1].lower() if "." in clean else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadValidationError("Unsupported file type. Upload a PDF, DOCX or TXT file.")
    if not data:
        raise UploadValidationError("The uploaded file is empty.")
    if len(data) > max_bytes:
        raise UploadValidationError(f"The file exceeds the maximum upload size of {max_bytes // (1024 * 1024)} MB.")
    declared = (declared_content_type or "").split(";")[0].strip().lower()
    allowed_types = ALLOWED_EXTENSIONS[ext]
    if declared and declared not in allowed_types and declared != "application/octet-stream":
        raise UploadValidationError(f"The file's content type ({declared}) does not match its .{ext} extension.")
    if not _sniff(ext, data):
        raise UploadValidationError(f"The file content is not a valid .{ext} file.")
    return ValidatedUpload(
        original_filename=clean,
        ext=ext,
        content_type=next(iter(allowed_types)),
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _sections(text: str) -> list[dict]:
    """Split long non-paginated text into labelled sections (no page numbers are claimed)."""
    paragraphs = [p for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    sections: list[str] = []
    buf: list[str] = []
    size = 0
    for para in paragraphs:
        if size + len(para) > SECTION_CHARS and buf:
            sections.append("\n".join(buf))
            buf, size = [], 0
        buf.append(para)
        size += len(para) + 1
    if buf:
        sections.append("\n".join(buf))
    return [{"page": None, "label": f"Section {i}", "text": s} for i, s in enumerate(sections, start=1)]


def extract_pdf(data: bytes) -> ExtractionResult:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:  # noqa: BLE001 - any decrypt failure means we cannot read it
                return ExtractionResult("failed", "The PDF is password-protected and cannot be read.")
        total_pages = len(reader.pages)
        if total_pages > MAX_PAGES:
            return ExtractionResult("failed", f"The PDF has more than {MAX_PAGES} pages, which is not supported.")
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 - a single broken page should not fail the document
                text = ""
            pages.append({"page": i, "label": f"Page {i}", "text": _clean_text(text)})
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        return ExtractionResult("failed", f"The PDF could not be parsed ({type(exc).__name__}).")

    chars = sum(len(str(p["text"])) for p in pages)
    if total_pages and chars < MIN_CHARS_PER_PAGE_FOR_TEXT_LAYER * total_pages * 0.5:
        return ExtractionResult(
            "needs_ocr",
            "Little or no selectable text was found - this looks like a scanned PDF. OCR is not configured on "
            "this server, so no text was extracted. Upload a text-based PDF, DOCX or TXT version instead.",
            pages=[p for p in pages if p["text"]],
            page_count=total_pages,
        )
    return ExtractionResult(
        "processed",
        f"Extracted text from {total_pages} page(s).",
        pages=[p for p in pages if p["text"]],
        page_count=total_pages,
    )


def extract_docx(data: bytes) -> ExtractionResult:
    import docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = docx.Document(io.BytesIO(data))
    except (PackageNotFoundError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        return ExtractionResult("failed", f"The DOCX file could not be parsed ({type(exc).__name__}).")
    parts: list[str] = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells: list[str] = []
            for cell in row.cells:
                t = cell.text.strip()
                if t and (not cells or cells[-1] != t):
                    cells.append(t)
            if cells:
                parts.append(" | ".join(cells))
    text = _clean_text("\n".join(parts))
    if not text:
        return ExtractionResult("failed", "The DOCX file contains no readable text.")
    sections = _sections(text)
    return ExtractionResult("processed", f"Extracted text into {len(sections)} section(s). DOCX files have no fixed page numbers.", sections)


def extract_txt(data: bytes) -> ExtractionResult:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    text = _clean_text(text)
    if not text:
        return ExtractionResult("failed", "The text file is empty.")
    sections = _sections(text)
    return ExtractionResult("processed", f"Extracted text into {len(sections)} section(s).", sections)


def extract(ext: str, data: bytes) -> ExtractionResult:
    if ext == "pdf":
        return extract_pdf(data)
    if ext == "docx":
        return extract_docx(data)
    if ext == "txt":
        return extract_txt(data)
    return ExtractionResult("failed", "Unsupported file type.")
