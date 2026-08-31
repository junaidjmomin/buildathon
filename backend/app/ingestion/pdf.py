from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date, datetime
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class AgreementPdfError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedAgreementPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class ExtractedAgreementClause:
    """A numbered clause with page-local offsets in normalized extracted text."""

    clause_number: str
    clause_title: str
    text: str
    page_number: int
    start_offset: int
    end_offset: int
    effective_from: date
    effective_to: date | None = None
    end_page_number: int | None = None


_CLAUSE_HEADER = re.compile(
    r"^\s*(?:(?P<prefix>clause|section|article)\s+)?"
    r"(?P<number>(?:[A-Z]\d+(?:\.\d+)*|\d+(?:\.\d+)*|[IVXLCDM]+))"
    r"(?P<marker>[.)])?\s*(?:(?:[:\-–—])\s*)?(?P<title>.*?)\s*$",
    re.IGNORECASE,
)
_PAGE_FOOTER = re.compile(
    r"\n?\s*Synthetic merchant agreement for sl3dge evaluation\s*-\s*"
    r"not a real Razorpay contract\s*\|?\s*Page\s+\d+\s*$",
    re.IGNORECASE,
)


def _normalize_text(value: str) -> str:
    """Normalize PDF glyph text without changing its page-local line structure."""

    normalized = unicodedata.normalize("NFKC", value).replace("\x00", "")
    normalized = normalized.replace("\u00a0", " ").replace("\u00ad", "")
    return "\n".join(line.rstrip() for line in normalized.splitlines()).strip()


def _margin_signature(line: str) -> str:
    normalized = re.sub(r"\d+", "#", " ".join(line.casefold().split()))
    return normalized.strip(" |·-")


def _remove_repeated_margins(
    pages: list[ExtractedAgreementPage],
) -> list[ExtractedAgreementPage]:
    """Remove repeated short headers and footers before computing evidence offsets."""

    if len(pages) < 2:
        return pages
    candidates: Counter[str] = Counter()
    per_page: list[tuple[list[str], set[str]]] = []
    for page in pages:
        lines = page.text.splitlines()
        margin_lines = [*lines[:3], *lines[-3:]]
        signatures = {
            signature
            for line in margin_lines
            if len(line.strip()) <= 180 and (signature := _margin_signature(line))
        }
        candidates.update(signatures)
        per_page.append((lines, signatures))
    threshold = max(2, (len(pages) + 1) // 2)
    repeated = {signature for signature, count in candidates.items() if count >= threshold}
    if not repeated:
        return pages
    cleaned: list[ExtractedAgreementPage] = []
    for page, (lines, _) in zip(pages, per_page, strict=True):
        last_index = len(lines) - 1
        kept = [
            line
            for index, line in enumerate(lines)
            if not (
                (index < 3 or index > last_index - 3)
                and _margin_signature(line) in repeated
            )
        ]
        cleaned.append(
            ExtractedAgreementPage(page_number=page.page_number, text="\n".join(kept).strip())
        )
    return cleaned


def _looks_like_title(value: str) -> bool:
    title = " ".join(value.split())
    return 1 < len(title) <= 240 and bool(re.search(r"[A-Za-z]", title))


def _clause_headings(lines: list[str]) -> list[tuple[int, str, str]]:
    """Return line index, normalized clause number and title for common legal headings."""

    headings: list[tuple[int, str, str]] = []
    for index, line in enumerate(lines):
        match = _CLAUSE_HEADER.match(line.strip())
        if match is None:
            continue
        number = match.group("number").upper()
        marker = match.group("marker")
        prefix = match.group("prefix")
        # A bare integer is usually a page number or amount. Require explicit
        # legal-heading syntax before treating it as a clause.
        if not (prefix or marker or "." in number or number[:1].isalpha()):
            continue
        title = " ".join(match.group("title").split())
        if not title and index + 1 < len(lines) and _looks_like_title(lines[index + 1]):
            title = " ".join(lines[index + 1].split())
        if not _looks_like_title(title):
            continue
        headings.append((index, number, title))
    return headings


def _append_continuation(
    clauses: list[ExtractedAgreementClause],
    *,
    text: str,
    page_number: int,
) -> bool:
    continuation = text.strip()
    if not clauses or not continuation:
        return False
    previous = clauses[-1]
    clauses[-1] = replace(
        previous,
        text=f"{previous.text}\n{continuation}",
        end_page_number=page_number,
        end_offset=len(continuation),
    )
    return True


def infer_agreement_effective_from(pages: list[ExtractedAgreementPage], *, fallback: date) -> date:
    """Read the agreement's stated effective date, falling back to intake metadata."""

    text = "\n".join(page.text for page in pages)
    match = re.search(
        r"effective\s+date\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if match:
        try:
            return datetime.strptime(
                f"{match.group(1)} {match.group(2)} {match.group(3)}",
                "%d %B %Y",
            ).date()
        except ValueError:
            pass
    return fallback


def segment_agreement_clauses(
    pages: list[ExtractedAgreementPage], *, agreement_effective_from: date
) -> list[ExtractedAgreementClause]:
    """Segment normalized PDF text into numbered clauses, retaining provenance.

    Clause boundaries are explicit numbered headings rather than page boundaries.
    Offsets refer to the normalized page text returned by ``extract_agreement_pages``;
    this makes the evidence reproducible even when a PDF extractor changes whitespace.
    """

    clauses: list[ExtractedAgreementClause] = []
    for page in pages:
        page_text = _PAGE_FOOTER.sub("", page.text).strip()
        lines = page_text.splitlines()
        if not lines:
            continue
        offsets: list[int] = []
        cursor = 0
        for line in lines:
            offsets.append(cursor)
            cursor += len(line) + 1
        matches = _clause_headings(lines)
        if not matches:
            if _append_continuation(
                clauses,
                text=page_text,
                page_number=page.page_number,
            ):
                continue
            clauses.append(
                ExtractedAgreementClause(
                    clause_number=f"UNNUMBERED_{page.page_number}",
                    clause_title="Unnumbered extracted text",
                    text=page_text,
                    page_number=page.page_number,
                    start_offset=0,
                    end_offset=len(page_text),
                    effective_from=agreement_effective_from,
                    end_page_number=page.page_number,
                )
            )
            continue
        first_start = matches[0][0]
        leading_text = "\n".join(lines[:first_start]).strip()
        if leading_text and not _append_continuation(
            clauses,
            text=leading_text,
            page_number=page.page_number,
        ):
            clauses.append(
                ExtractedAgreementClause(
                    clause_number=f"UNNUMBERED_{page.page_number}",
                    clause_title="Unnumbered extracted text",
                    text=leading_text,
                    page_number=page.page_number,
                    start_offset=0,
                    end_offset=len(leading_text),
                    effective_from=agreement_effective_from,
                    end_page_number=page.page_number,
                )
            )
        for match_index, (start_index, clause_number, clause_title) in enumerate(matches):
            end_index = (
                matches[match_index + 1][0] if match_index + 1 < len(matches) else len(lines)
            )
            chunk = "\n".join(lines[start_index:end_index]).strip()
            chunk = _PAGE_FOOTER.sub("", chunk).strip()
            if not chunk:
                continue
            start_offset = offsets[start_index]
            end_offset = start_offset + len(chunk)
            effective_from = agreement_effective_from
            date_match = re.search(
                r"(?:effective\s+(?:date|from)|captured\s+(?:from|on\s+or\s+after))\s+"
                r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
                chunk,
                re.IGNORECASE,
            )
            if date_match:
                try:
                    effective_from = datetime.strptime(
                        f"{date_match.group(1)} {date_match.group(2)} {date_match.group(3)}",
                        "%d %B %Y",
                    ).date()
                except ValueError:
                    effective_from = agreement_effective_from
            clauses.append(
                ExtractedAgreementClause(
                    clause_number=clause_number,
                    clause_title=clause_title,
                    text=chunk,
                    page_number=page.page_number,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    effective_from=effective_from,
                    end_page_number=page.page_number,
                )
            )
    return clauses


def extract_agreement_pages(
    content: bytes,
    *,
    max_pages: int,
    max_page_content_bytes: int,
    max_extracted_chars: int,
) -> list[ExtractedAgreementPage]:
    header_offset = content.find(b"%PDF-", 0, min(len(content), 1024))
    if header_offset < 0:
        raise AgreementPdfError("Agreement file is not a valid PDF")
    pdf_content = content[header_offset:]
    try:
        reader = PdfReader(BytesIO(pdf_content), strict=True)
    except (PdfReadError, ValueError, TypeError) as exc:
        try:
            # Many digitally generated PDFs contain repairable cross-reference
            # defects. pypdf's non-strict mode recovers these without OCR.
            reader = PdfReader(BytesIO(pdf_content), strict=False)
        except (PdfReadError, ValueError, TypeError) as fallback_exc:
            raise AgreementPdfError("Agreement PDF could not be parsed safely") from fallback_exc
    if reader.is_encrypted:
        raise AgreementPdfError("Encrypted agreement PDFs are not supported")
    if not reader.pages:
        raise AgreementPdfError("Agreement PDF has no pages")
    if len(reader.pages) > max_pages:
        raise AgreementPdfError(f"Agreement PDF exceeds the {max_pages}-page limit")

    result: list[ExtractedAgreementPage] = []
    extracted_chars = 0
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > max_page_content_bytes:
                raise AgreementPdfError(
                    f"Agreement PDF page {page_number} exceeds the decompressed content limit"
                )
            raw_text = page.extract_text(extraction_mode="layout") or ""
            if not raw_text.strip():
                raw_text = page.extract_text() or ""
        except AgreementPdfError:
            raise
        except Exception as exc:
            raise AgreementPdfError(
                f"Agreement PDF page {page_number} could not be extracted"
            ) from exc
        text = _normalize_text(raw_text)
        extracted_chars += len(text)
        if extracted_chars > max_extracted_chars:
            raise AgreementPdfError("Agreement PDF exceeds the extracted-text limit")
        if text:
            result.append(ExtractedAgreementPage(page_number=page_number, text=text))
    if not result or sum(character.isalnum() for page in result for character in page.text) < 20:
        raise AgreementPdfError(
            "The PDF does not contain enough extractable text for agreement ingestion"
        )
    return _remove_repeated_margins(result)
