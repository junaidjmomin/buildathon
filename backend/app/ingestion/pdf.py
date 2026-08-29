from __future__ import annotations

import re
from dataclasses import dataclass
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


_CLAUSE_HEADER = re.compile(
    r"^\s*(?P<number>(?:\d+\.\d+|A\d+\.\d+))\s+(?P<title>[^|\n].*?)\s*$",
    re.IGNORECASE,
)
_PAGE_FOOTER = re.compile(
    r"\n?\s*Synthetic merchant agreement for sl3dge evaluation\s*-\s*"
    r"not a real Razorpay contract\s*\|?\s*Page\s+\d+\s*$",
    re.IGNORECASE,
)


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
        matches = [
            (index, match)
            for index, line in enumerate(lines)
            if (match := _CLAUSE_HEADER.match(line.strip())) is not None
        ]
        if not matches:
            # Some agreements contain prose without numbered headings. Keep the
            # text ingestible, but make the uncertainty explicit instead of
            # pretending the page itself is a clause.
            clauses.append(
                ExtractedAgreementClause(
                    clause_number=f"UNNUMBERED_{page.page_number}",
                    clause_title="Unnumbered extracted text",
                    text=page_text,
                    page_number=page.page_number,
                    start_offset=0,
                    end_offset=len(page_text),
                    effective_from=agreement_effective_from,
                )
            )
            continue
        for match_index, (start_index, match) in enumerate(matches):
            end_index = (
                matches[match_index + 1][0] if match_index + 1 < len(matches) else len(lines)
            )
            chunk = "\n".join(lines[start_index:end_index]).strip()
            chunk = _PAGE_FOOTER.sub("", chunk).strip()
            if not chunk:
                continue
            start_offset = offsets[start_index]
            end_offset = start_offset + len(chunk)
            clause_number = match.group("number").upper()
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
                    clause_title=match.group("title").strip(),
                    text=chunk,
                    page_number=page.page_number,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    effective_from=effective_from,
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
    if not content.startswith(b"%PDF-"):
        raise AgreementPdfError("Agreement file is not a valid PDF")
    try:
        reader = PdfReader(BytesIO(content), strict=True)
    except (PdfReadError, ValueError, TypeError) as exc:
        raise AgreementPdfError("Agreement PDF could not be parsed safely") from exc
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
        except AgreementPdfError:
            raise
        except Exception as exc:
            raise AgreementPdfError(
                f"Agreement PDF page {page_number} could not be extracted"
            ) from exc
        text = "\n".join(
            line.rstrip() for line in raw_text.replace("\x00", "").splitlines()
        ).strip()
        extracted_chars += len(text)
        if extracted_chars > max_extracted_chars:
            raise AgreementPdfError("Agreement PDF exceeds the extracted-text limit")
        if text:
            result.append(ExtractedAgreementPage(page_number=page_number, text=text))
    if not result:
        raise AgreementPdfError(
            "No text could be extracted; scanned agreements require an approved OCR workflow"
        )
    return result
