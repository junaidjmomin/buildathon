from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO

import polars as pl

MONEY_COLUMNS = {
    "amount",
    "actual_fee",
    "actual_tax",
    "actual_net",
    "bank_credit",
    "refund_amount",
    "refund_deduction",
    "unsupported_fee",
    "chargeback_fee",
}


@dataclass(frozen=True)
class ParsedCsv:
    row_count: int
    columns: list[str]
    decimal_values_checked: int


def parse_source_csv(content: bytes) -> ParsedCsv:
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
    return ParsedCsv(
        row_count=frame.height,
        columns=list(frame.columns),
        decimal_values_checked=decimal_values_checked,
    )
