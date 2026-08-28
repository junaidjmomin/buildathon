from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import PurePath

import polars as pl

MONEY_COLUMNS = {
    "amount",
    "credit",
    "debit",
    "fee",
    "tax",
    "gross_amount",
    "net_amount",
    "other_adjustment",
    "refund_adjustment",
    "actual_fee",
    "actual_tax",
    "actual_net",
    "bank_credit",
    "refund_amount",
    "refund_deduction",
    "unsupported_fee",
    "chargeback_fee",
}

SOURCE_SIGNATURES: dict[str, set[str]] = {
    "ORDERS": {"order_id", "customer_id", "amount"},
    "PAYMENTS": {"payment_id", "amount"},
    "REFUNDS": {"refund_id", "payment_id", "amount"},
    "SETTLEMENTS": {
        "settlement_id",
        "payment_id",
        "net_amount",
    },
    "CHARGEBACKS": {"chargeback_id", "payment_id", "amount"},
    "BANK_RECONCILIATION": {
        "bank_txn_id",
        "credit",
        "debit",
    },
}

FILENAME_HINTS = {
    "orders": "ORDERS",
    "payments": "PAYMENTS",
    "refunds": "REFUNDS",
    "settlements": "SETTLEMENTS",
    "chargebacks": "CHARGEBACKS",
    "bank": "BANK_RECONCILIATION",
    "reconciliation": "BANK_RECONCILIATION",
    "recon": "BANK_RECONCILIATION",
}


@dataclass(frozen=True)
class ParsedCsv:
    row_count: int
    columns: list[str]
    decimal_values_checked: int
    source_type: str
    classification_confidence: Decimal
    classification_evidence: list[str]


@dataclass(frozen=True)
class SourceCsvDocument:
    metadata: ParsedCsv
    rows: list[dict[str, str]]


def parse_source_csv(content: bytes, *, filename: str | None = None) -> ParsedCsv:
    if not content:
        raise ValueError("CSV file is empty")
    if b"\x00" in content:
        raise ValueError("CSV file contains binary data")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV file must be UTF-8 encoded") from exc
    header = next(csv.reader(StringIO(decoded)), [])
    normalized_header = [column.strip() for column in header]
    if not normalized_header or any(not column for column in normalized_header):
        raise ValueError("CSV file must include non-empty column names")
    if len(set(normalized_header)) != len(normalized_header):
        raise ValueError("CSV file contains duplicate column names")
    if len(normalized_header) > 200:
        raise ValueError("CSV file exceeds the 200-column limit")
    try:
        frame = pl.read_csv(BytesIO(content), infer_schema=False)
    except Exception as exc:
        raise ValueError("CSV file could not be parsed") from exc
    if not frame.columns:
        raise ValueError("CSV file must include a header row")
    if frame.height > 100_000:
        raise ValueError("CSV file exceeds the 100,000-row limit")
    for column in frame.columns:
        lengths = frame.get_column(column).drop_nulls().str.len_bytes()
        if lengths.len() and lengths.max() > 10_000:
            raise ValueError(f"Column {column} contains a value exceeding 10,000 bytes")
    decimal_values_checked = 0
    for column in MONEY_COLUMNS.intersection(frame.columns):
        for raw in frame.get_column(column).drop_nulls().to_list():
            value = str(raw).strip()
            if not value:
                continue
            try:
                parsed = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError(f"Column {column} contains an invalid decimal amount") from exc
            if not parsed.is_finite():
                raise ValueError(f"Column {column} contains a non-finite decimal amount")
            decimal_values_checked += 1
    source_type, confidence, evidence = classify_source_csv(frame, filename=filename)
    return ParsedCsv(
        row_count=frame.height,
        columns=list(frame.columns),
        decimal_values_checked=decimal_values_checked,
        source_type=source_type,
        classification_confidence=confidence,
        classification_evidence=evidence,
    )


def read_source_csv(content: bytes, *, filename: str | None = None) -> SourceCsvDocument:
    """Validate and read a source CSV while preserving every value as text.

    Monetary values intentionally remain strings until the canonical mapper parses
    them with :class:`Decimal`; Polars is used only by the validation pass.
    """

    metadata = parse_source_csv(content, filename=filename)
    decoded = content.decode("utf-8-sig")
    reader = csv.DictReader(StringIO(decoded))
    rows = [
        {(key or "").strip(): (value or "").strip() for key, value in row.items()} for row in reader
    ]
    return SourceCsvDocument(metadata=metadata, rows=rows)


def classify_source_csv(
    frame: pl.DataFrame,
    *,
    filename: str | None = None,
) -> tuple[str, Decimal, list[str]]:
    columns = {column.strip().lower() for column in frame.columns}
    matches = [
        (source_type, signature)
        for source_type, signature in SOURCE_SIGNATURES.items()
        if signature.issubset(columns)
    ]
    if matches:
        most_specific = max(len(signature) for _, signature in matches)
        matches = [match for match in matches if len(match[1]) == most_specific]
    if len(matches) != 1:
        if not matches:
            return (
                "UNRESOLVED",
                Decimal("0"),
                ["No supported source schema signature matched the CSV columns."],
            )
        return (
            "UNRESOLVED",
            Decimal("0"),
            ["More than one source schema signature matched; manual review is required."],
        )

    source_type, signature = matches[0]
    evidence = [f"Required {source_type.lower()} columns matched: {', '.join(sorted(signature))}."]
    confidence = Decimal("0.98")
    hint = _filename_hint(filename)
    if hint == source_type:
        confidence = Decimal("0.99")
        evidence.append("The filename hint agrees with the content-derived classification.")
    elif hint is not None:
        confidence = Decimal("0.95")
        evidence.append(
            "The filename suggests "
            f"{hint}, but content columns deterministically identify {source_type}."
        )
    else:
        evidence.append("Classification is based on CSV content; no filename hint was required.")
    return source_type, confidence, evidence


def _filename_hint(filename: str | None) -> str | None:
    if not filename:
        return None
    stem = PurePath(filename).stem.lower()
    for token, source_type in FILENAME_HINTS.items():
        if token in stem:
            return source_type
    return None
