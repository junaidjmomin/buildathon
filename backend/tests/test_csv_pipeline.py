from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.domain.models import FinancialEvent
from app.ingestion.csv import read_source_csv
from app.ingestion.pipeline import (
    MATCH_THRESHOLD,
    _canonicalize,
    _drop_invalid_rows,
    _match_score,
)


def _document(name: str, content: bytes):
    return (name, name, read_source_csv(content, filename=name))


def test_documented_six_file_bundle_builds_deterministic_graph() -> None:
    docs_root = Path(__file__).parents[2] / "docs"
    documents = []
    for stem in ("orders", "payments", "refunds", "settlements", "chargebacks", "bank"):
        path = docs_root / f"{stem}.csv"
        documents.append(_document(path.name, path.read_bytes()))

    events, edges, unresolved = _canonicalize(
        documents,
        run_id="RUN_TEST_CSV",
        completed_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )

    assert len(events) == 145
    assert len(edges) == 132
    # Every settlement in the documented bundle either carries a bank credit or
    # has no amount-compatible credit anywhere. Absence is a deterministic
    # conclusion (MISSING_BANK_CREDIT), not an unresolved relationship, so no
    # settlement here is genuinely ambiguous.
    assert unresolved == 0
    assert sum(event.event_type == "PAYMENT" for event in events) == 60
    assert sum(event.event_type == "SETTLEMENT" for event in events) == 10
    assert sum(event.event_type == "UNRESOLVED_MATCH" for event in events) == unresolved
    assert sum(event.event_type == "MISSING_BANK_CREDIT" for event in events) == 1
    assert sum(edge.relationship == "INCLUDED_IN" for edge in edges) == 60
    assert sum(edge.relationship == "CREDITED_AS" for edge in edges) == 9
    # Deterministic matching methods: exact reference, fuzzy composite, or
    # the unique-amount fallback. Every bank edge records its authority.
    assert all(edge.method in {"EXACT", "FUZZY", "AMOUNT_UNIQUE"} for edge in edges)
    for edge in edges:
        if edge.relationship == "CREDITED_AS":
            assert edge.evidence.get("authority") == "DETERMINISTIC"


def test_embedded_settlement_reference_in_narration_is_matched() -> None:
    """A bank narration carrying the settlement id inside a delimited string.

    Tokenization must split on ``/`` so the settlement reference is a real
    token rather than being swallowed into one opaque blob.
    """

    payments = (
        b"payment_id,amount,captured_at,payment_method,card_scope,fee,tax,status\n"
        b"PAY_TOKEN_1,100.00,2026-08-01T10:00:00,card,domestic,1.55,0.28,captured\n"
    )
    settlements = (
        b"settlement_id,payment_id,net_amount,settled_at\n"
        b"SET_TOKEN_1,PAY_TOKEN_1,98.17,2026-08-03T10:00:00\n"
    )
    bank = (
        b"bank_txn_id,credit,debit,posted_at,reference,description\n"
        b"BANK_TOKEN_1,98.17,0.00,2026-08-04T10:00:00,,RZP/SET_TOKEN_1/SETTLEMENT\n"
    )

    events, edges, unresolved = _canonicalize(
        [
            _document("payments.csv", payments),
            _document("settlements.csv", settlements),
            _document("bank.csv", bank),
        ],
        run_id="RUN_TOKENIZED",
        completed_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )

    assert unresolved == 0
    credited = [edge for edge in edges if edge.relationship == "CREDITED_AS"]
    assert len(credited) == 1
    assert credited[0].method == "EXACT"
    assert credited[0].evidence["reference_token_overlap"] == "1.0000"
    assert not any(event.event_type == "MISSING_BANK_CREDIT" for event in events)


def test_amount_unique_fallback_matches_only_when_both_sides_are_unique() -> None:
    """No textual link at all: uniqueness of the amount is the only evidence.

    The pairing resolves when exactly one unmatched credit and exactly one
    unmatched settlement share the amount. A second settlement sharing that
    amount destroys uniqueness and both stay unresolved.
    """

    payments = (
        b"payment_id,amount,captured_at,payment_method,card_scope,fee,tax,status\n"
        b"PAY_UNIQ_1,100.00,2026-08-01T10:00:00,card,domestic,1.55,0.28,captured\n"
        b"PAY_UNIQ_2,100.00,2026-08-01T11:00:00,card,domestic,1.55,0.28,captured\n"
    )
    settlements_unique = (
        b"settlement_id,payment_id,net_amount,settled_at\n"
        b"SET_UNIQ_1,PAY_UNIQ_1,98.17,2026-08-03T10:00:00\n"
    )
    settlements_tied = settlements_unique + b"SET_UNIQ_2,PAY_UNIQ_2,98.17,2026-08-03T11:00:00\n"
    bank = (
        b"bank_txn_id,credit,debit,posted_at,reference,description\n"
        b"BANK_UNIQ_1,98.17,0.00,2026-08-04T10:00:00,,PAYMENT AGGREGATOR CREDIT\n"
    )

    _, unique_edges, unique_unresolved = _canonicalize(
        [
            _document("payments.csv", payments),
            _document("settlements.csv", settlements_unique),
            _document("bank.csv", bank),
        ],
        run_id="RUN_AMOUNT_UNIQUE",
        completed_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )
    credited = [edge for edge in unique_edges if edge.relationship == "CREDITED_AS"]
    assert unique_unresolved == 0
    assert len(credited) == 1
    assert credited[0].method == "AMOUNT_UNIQUE"
    assert credited[0].evidence["matched_on"] == "unique_amount"

    _, tied_edges, tied_unresolved = _canonicalize(
        [
            _document("payments.csv", payments),
            _document("settlements.csv", settlements_tied),
            _document("bank.csv", bank),
        ],
        run_id="RUN_AMOUNT_TIED",
        completed_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )
    # Two settlements share the amount: the single credit cannot be attributed
    # to either, so both remain unresolved rather than being force-matched.
    assert not any(edge.relationship == "CREDITED_AS" for edge in tied_edges)
    assert tied_unresolved == 2


def test_fuzzy_score_is_explicit_and_deterministic() -> None:
    settlement = _event("settlement", "SET_001", "100.00", "2026-08-05T10:00:00+00:00")
    bank = _event(
        "bank",
        "BANK_1",
        "100.00",
        "2026-08-06T10:00:00+00:00",
        reference="set 001 batch",
        description="merchant payout",
    )

    score, evidence = _match_score(settlement, bank)

    assert score >= MATCH_THRESHOLD
    assert evidence["confidence_score"] == str(score)
    assert evidence["amount_within_tolerance"] is True
    assert evidence["reference_token_overlap"] == "1.0000"
    assert evidence["authority"] == "DETERMINISTIC"


def test_ambiguous_equal_candidates_remain_unresolved() -> None:
    payments = (
        b"payment_id,amount,captured_at,payment_method,card_scope,fee,tax,status\n"
        b"PAY_1,100.00,2026-08-01T10:00:00,card,domestic,1.55,0.28,captured\n"
    )
    settlements = (
        b"settlement_id,payment_id,net_amount,settled_at\nSET_1,PAY_1,98.17,2026-08-03T10:00:00\n"
    )
    bank = (
        b"bank_txn_id,credit,debit,posted_at,reference,description\n"
        b"BANK_1,98.17,0.00,2026-08-04T10:00:00,SET_1,payout\n"
        b"BANK_2,98.17,0.00,2026-08-04T10:00:00,SET_1,payout\n"
    )

    events, edges, unresolved = _canonicalize(
        [
            _document("payments.csv", payments),
            _document("settlements.csv", settlements),
            _document("bank.csv", bank),
        ],
        run_id="RUN_AMBIGUOUS",
        completed_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )

    assert unresolved == 1
    assert not any(edge.relationship == "CREDITED_AS" for edge in edges)
    unresolved_event = next(event for event in events if event.event_type == "UNRESOLVED_MATCH")
    assert unresolved_event.status == "unresolved"
    assert unresolved_event.normalized_payload["decision"] == "UNRESOLVED"
    assert unresolved_event.normalized_payload["candidate_bank_references"] == [
        "BANK_2",
        "BANK_1",
    ]


def test_row_filter_recomputes_errors_beyond_response_cap() -> None:
    rows = [",100.00,2026-08-01T10:00:00,card,domestic,1.55,0.28,captured" for _ in range(60)]
    content = (
        "payment_id,amount,captured_at,payment_method,card_scope,fee,tax,status\n"
        + "\n".join(rows)
        + "\n"
    ).encode()
    document = read_source_csv(content, filename="payments.csv")
    assert document.metadata.row_error_count == 60
    assert len(document.metadata.row_errors) == 50
    filtered, dropped = _drop_invalid_rows([("UPLOAD", "payments.csv", document)])
    assert dropped == 60
    assert filtered[0][2].rows == []


def _event(
    event_type: str,
    external_id: str,
    amount: str,
    timestamp: str,
    *,
    reference: str = "",
    description: str = "",
) -> FinancialEvent:
    return FinancialEvent(
        id=f"test:{event_type}:{external_id}",
        run_id="RUN_TEST",
        source="TEST",
        external_id=external_id,
        event_type=event_type.upper(),
        amount=Decimal(amount),
        currency="INR",
        timestamp=datetime.fromisoformat(timestamp),
        raw_payload={},
        normalized_payload={"reference": reference, "description": description},
    )
