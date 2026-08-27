from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class AgreementPdfError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedAgreementPage:
    page_number: int
    text: str


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
