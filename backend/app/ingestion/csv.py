from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
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

SCHEMA_COLUMNS: dict[str, set[str]] = {
    "ORDERS": {"order_id", "customer_id", "payment_id", "amount", "currency", "created_at"},
    "PAYMENTS": {
        "payment_id",
        "order_id",
        "amount",
        "currency",
        "payment_method",
        "card_network",
        "card_scope",
        "captured_at",
        "fee",
        "tax",
        "status",
    },
    "REFUNDS": {"refund_id", "payment_id", "amount", "currency", "created_at", "status"},
    "SETTLEMENTS": {
        "settlement_id",
        "payment_id",
        "net_amount",
        "currency",
        "settled_at",
        "status",
    },
    "CHARGEBACKS": {
        "chargeback_id",
        "payment_id",
        "amount",
        "currency",
        "created_at",
        "fee",
        "status",
    },
    "BANK_RECONCILIATION": {
        "bank_txn_id",
        "settlement_id",
        "credit",
        "debit",
        "currency",
        "posted_at",
        "reference",
        "description",
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

# The identifier column whose emptiness makes a row unusable at execution time.
REQUIRED_ID_COLUMNS: dict[str, str] = {
    "ORDERS": "order_id",
    "PAYMENTS": "payment_id",
    "REFUNDS": "refund_id",
    "SETTLEMENTS": "settlement_id",
    "CHARGEBACKS": "chargeback_id",
    "BANK_RECONCILIATION": "bank_txn_id",
}

TIMESTAMP_COLUMNS: dict[str, str] = {
    "ORDERS": "created_at",
    "PAYMENTS": "captured_at",
    "REFUNDS": "created_at",
    "SETTLEMENTS": "settled_at",
    "CHARGEBACKS": "created_at",
    "BANK_RECONCILIATION": "posted_at",
}

# Row errors are reported per file; only the first few are surfaced so a
# corrupt upload cannot produce an unbounded response payload.
MAX_ROW_ERRORS = 50


@dataclass(frozen=True)
class CsvRowError:
    row_number: int
    column: str
    message: str


@dataclass(frozen=True)
class ParsedCsv:
    row_count: int
    columns: list[str]
    decimal_values_checked: int
    source_type: str
    classification_confidence: Decimal
    classification_evidence: list[str]
    row_errors: list[CsvRowError] = field(default_factory=list)
    row_error_count: int = 0
    schema_drift: bool = False
    drift_columns: list[str] = field(default_factory=list)


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
    source_type, confidence, evidence = classify_source_csv(frame, filename=filename)
    observed_columns = {column.strip().lower() for column in frame.columns}
    drift_columns = (
        sorted(observed_columns - SCHEMA_COLUMNS.get(source_type, set()))
        if source_type != "UNRESOLVED"
        else []
    )
    if drift_columns:
        evidence = [
            *evidence,
            f"Schema drift detected in unmapped columns: {', '.join(drift_columns)}.",
        ]
    row_errors, row_error_count = _collect_row_errors(frame, source_type)
    for column in MONEY_COLUMNS.intersection(frame.columns):
        for raw in frame.get_column(column).drop_nulls().to_list():
            value = str(raw).strip()
            if not value:
                continue
            try:
                parsed = Decimal(value)
            except InvalidOperation:
                # Already reported per-row by _collect_row_errors; do not
                # reject the whole file here because classification can
                # still succeed for the remaining valid rows.
                continue
            if not parsed.is_finite():
                continue
            decimal_values_checked += 1
    return ParsedCsv(
        row_count=frame.height,
        columns=list(frame.columns),
        decimal_values_checked=decimal_values_checked,
        source_type=source_type,
        classification_confidence=confidence,
        classification_evidence=evidence,
        row_errors=row_errors,
        row_error_count=row_error_count,
        schema_drift=bool(drift_columns),
        drift_columns=drift_columns,
    )


def _collect_row_errors(frame: pl.DataFrame, source_type: str) -> tuple[list[CsvRowError], int]:
    """Report invalid rows without rejecting the classifiable file.

    A single malformed money value or an empty required identifier used to
    abort the whole upload with a column-level message. The rows are now
    collected with their row numbers so execution can fail closed later with
    precise errors, while still-unrelated valid rows keep the file acceptable
    for classification.
    """

    errors: list[CsvRowError] = []
    total = 0
    id_column = REQUIRED_ID_COLUMNS.get(source_type)

    def report(row_number: int, column: str, message: str) -> None:
        nonlocal total
        total += 1
        if len(errors) < MAX_ROW_ERRORS:
            errors.append(CsvRowError(row_number=row_number, column=column, message=message))

    text_rows = frame.iter_rows(named=True)
    for row_number, row in enumerate(text_rows, start=2):
        if id_column is not None:
            identifier = str(row.get(id_column) or "").strip()
            if not identifier:
                report(
                    row_number,
                    id_column,
                    f"missing required identifier {id_column}",
                )
        timestamp_column = TIMESTAMP_COLUMNS.get(source_type)
        if timestamp_column is not None:
            raw_timestamp = str(row.get(timestamp_column) or "").strip()
            if not raw_timestamp:
                report(
                    row_number,
                    timestamp_column,
                    f"missing required timestamp {timestamp_column}",
                )
            else:
                try:
                    datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
                except ValueError:
                    report(
                        row_number,
                        timestamp_column,
                        f"invalid ISO-8601 timestamp '{raw_timestamp}'",
                    )
        for column in MONEY_COLUMNS.intersection(frame.columns):
            raw = row.get(column)
            value = str(raw).strip() if raw is not None else ""
            if not value:
                continue
            try:
                parsed = Decimal(value)
            except InvalidOperation:
                report(row_number, column, f"invalid decimal amount '{value}'")
                continue
            if not parsed.is_finite():
                report(row_number, column, f"non-finite decimal amount '{value}'")
    return errors, total


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
