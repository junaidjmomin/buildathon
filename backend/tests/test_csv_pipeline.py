from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.domain.models import FinancialEvent
from app.ingestion.csv import read_source_csv
from app.ingestion.pipeline import MATCH_THRESHOLD, _canonicalize, _match_score


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
    assert unresolved == 1
    assert sum(event.event_type == "PAYMENT" for event in events) == 60
    assert sum(event.event_type == "SETTLEMENT" for event in events) == 10
    assert sum(event.event_type == "UNRESOLVED_MATCH" for event in events) == 1
    assert sum(edge.relationship == "INCLUDED_IN" for edge in edges) == 60
    assert all(edge.method in {"EXACT", "FUZZY"} for edge in edges)


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
    payments = b"payment_id,amount,captured_at,payment_method,card_scope,fee,tax,status\nPAY_1,100.00,2026-08-01T10:00:00,card,domestic,1.55,0.28,captured\n"
    settlements = b"settlement_id,payment_id,net_amount,settled_at\nSET_1,PAY_1,98.17,2026-08-03T10:00:00\n"
    bank = b"bank_txn_id,credit,debit,posted_at,reference,description\nBANK_1,98.17,0.00,2026-08-04T10:00:00,SET_1,payout\nBANK_2,98.17,0.00,2026-08-04T10:00:00,SET_1,payout\n"

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
