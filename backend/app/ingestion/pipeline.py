from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from hashlib import sha256
from time import perf_counter
from typing import Any

from app.controls.live import LiveControlEvaluation, build_live_control_evaluations
from app.core.money import money
from app.domain.models import (
    CanonicalEventEdge,
    CaseEvidence,
    ControlType,
    FinancialEvent,
    RootCause,
    SourceRunResponse,
)
from app.ingestion.csv import SourceCsvDocument
from app.integrations.razorpay.sync import live_controls_for_tenant
from app.persistence.database import session_scope
from app.persistence.repository import (
    CaseRepository,
    ControlEvaluationRepository,
    RunRepository,
    SourceSnapshotRepository,
)

MATCH_THRESHOLD = Decimal("0.80")
AMBIGUITY_MARGIN = Decimal("0.05")
AMOUNT_TOLERANCE = Decimal("0.01")


def execute_source_run(
    documents: list[tuple[str, str, SourceCsvDocument]],
    *,
    tenant_id: str,
    actor_id: str,
    request_id: str | None,
    run_name: str | None = None,
) -> SourceRunResponse:
    """Execute the deterministic pipeline for an already validated CSV bundle.

    Each tuple contains ``(artifact_id, filename, document)``. The artifact bytes
    are validated by the API before this function is called. Matching is scored
    and deterministic; no LLM participates in canonical edge creation.
    """

    started = perf_counter()
    _validate_bundle(documents)
    fingerprint = sha256(
        "|".join(
            sorted(
                f"{artifact_id}:{document.metadata.source_type}"
                for artifact_id, _, document in documents
            )
        ).encode()
    ).hexdigest()
    run_id = f"RUN_CSV_{fingerprint[:20].upper()}"
    sync_id = f"CSV_INGEST_{fingerprint[:20].upper()}"
    completed_at = datetime.now(timezone.utc)
    events, edges, unresolved = _canonicalize(documents, run_id=run_id, completed_at=completed_at)
    controls = live_controls_for_tenant(tenant_id)

    with session_scope(tenant_id=tenant_id) as session:
        snapshots = SourceSnapshotRepository(session)
        snapshot_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
        snapshot_items: list[dict[str, Any]] = []
        snapshot_keys: list[tuple[str, str]] = []
        for artifact_id, filename, document in documents:
            source_type = document.metadata.source_type
            id_column = _id_column(source_type)
            for row_number, row in enumerate(document.rows, start=2):
                external_id = row.get(id_column, "") or f"row-{row_number}"
                snapshot_keys.append((source_type, external_id))
                snapshot_items.append(
                    {
                        "source_system": "CSV_UPLOAD",
                        "resource_type": source_type.lower(),
                        "external_id": external_id,
                        "payload": row,
                        "provenance": {
                            "artifact_id": artifact_id,
                            "filename": filename,
                            "row_number": row_number,
                            "classification_confidence": str(
                                document.metadata.classification_confidence
                            ),
                            "classifier": "deterministic-schema-v1",
                        },
                        "captured_at": completed_at,
                        "run_id": run_id,
                        "source_created_at": _row_timestamp(row, source_type, required=False),
                    }
                )
        captured = snapshots.capture_many(tenant_id=tenant_id, items=snapshot_items)
        for key, snapshot in zip(snapshot_keys, captured, strict=True):
            snapshot_ids[key].append(snapshot.id)

        persisted_events = []
        for event in events:
            event_type = event.event_type
            source_key = "BANK_RECONCILIATION" if event_type.startswith("BANK_") else event_type
            persisted_events.append(
                event.model_copy(
                    update={
                        "normalized_payload": {
                            **event.normalized_payload,
                            "source_snapshot_ids": snapshot_ids.get(
                                (source_key, event.external_id), []
                            ),
                        }
                    }
                )
            )

        run_repository = RunRepository(session)
        run_repository.save_canonical_sync(
            run_id=run_id,
            sync_id=sync_id,
            synced_at=completed_at,
            events=persisted_events,
            edges=edges,
            tenant_id=tenant_id,
            run_name=run_name or f"Uploaded CSV control run · {completed_at:%d %b %Y %H:%M UTC}",
            source="CSV_UPLOAD",
            manifest_extra={
                "artifact_ids": [artifact_id for artifact_id, _, _ in documents],
                "source_types": sorted(
                    document.metadata.source_type for _, _, document in documents
                ),
                "unresolved_matches": unresolved,
                "pipeline_version": "csv-deterministic-v1",
            },
        )
        run_repository.save_controls(controls, tenant_id=tenant_id)
        session.flush()
        evaluations = build_live_control_evaluations(persisted_events, edges, controls)
        roots = _build_root_causes(run_id, evaluations)
        root_by_type = {root.category: root for root in roots}
        evaluation_repository = ControlEvaluationRepository(session)
        for evaluation in evaluations:
            evaluation_repository.save(
                tenant_id=tenant_id,
                run_id=run_id,
                evaluation_id=evaluation.evaluation_id,
                control_id=evaluation.control.id,
                control_version=evaluation.control.version,
                target_type=evaluation.target_type,
                target_id=evaluation.target_id,
                outcome=evaluation.outcome.value,
                expected_amount=evaluation.expected_amount,
                actual_amount=evaluation.actual_amount,
                tolerance_amount=evaluation.tolerance_amount,
                difference_amount=evaluation.difference_amount,
                financial_impact=evaluation.financial_impact,
                confidence=Decimal("1"),
                input_fingerprint=evaluation.input_fingerprint,
                engine_version="sl3dge-deterministic-v1",
                source_snapshot_ids=evaluation.source_snapshot_ids,
                evidence=evaluation.evidence,
                evaluated_at=completed_at,
            )
            if evaluation.violation is not None:
                root = root_by_type.get(evaluation.control.control_type.value)
                run_repository.save_violation(
                    evaluation.violation.model_copy(
                        update={"root_cause_id": root.id if root else None}
                    ),
                    run_id=run_id,
                    tenant_id=tenant_id,
                )
        for root in roots:
            run_repository.save_root_cause(root, run_id=run_id, tenant_id=tenant_id)
        session.flush()
        case_repository = CaseRepository(session)
        for root in roots:
            related_evaluations = [
                item
                for item in evaluations
                if item.control.control_type.value == root.category and item.violation is not None
            ]
            related_violations = [
                item.violation.model_copy(update={"root_cause_id": root.id})
                for item in related_evaluations
                if item.violation is not None
            ]
            evidence = [
                CaseEvidence(
                    id=f"EVID_{item.evaluation_id}",
                    kind="CONTROL_EVALUATION",
                    title=item.control.name,
                    summary=(
                        f"Expected {item.expected_amount}; observed {item.actual_amount}; "
                        f"difference {item.difference_amount}."
                    ),
                    source_id=(
                        item.source_snapshot_ids[0] if item.source_snapshot_ids else item.event.id
                    ),
                    verified=True,
                )
                for item in related_evaluations
            ]
            case_repository.create_from_investigation(
                tenant_id=tenant_id,
                case_id=f"CASE_{root.id.removeprefix('RC_')}",
                root_cause=root,
                violations=related_violations,
                evidence=evidence,
                actor_id=actor_id,
            )

        processing_ms = max(1, int((perf_counter() - started) * 1000))
        run_repository.finalize_live_run(
            tenant_id=tenant_id,
            run_id=run_id,
            control_evaluation_count=len(evaluations),
            processing_ms=processing_ms,
        )
        run_repository.write_audit(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="CSV_CONTROL_RUN_COMPLETED",
            resource_type="run",
            resource_id=run_id,
            outcome="COMPLETE",
            details={
                "files_ingested": len(documents),
                "events_created": len(persisted_events),
                "edges_created": len(edges),
                "control_evaluations_created": len(evaluations),
                "violations_created": sum(item.violation is not None for item in evaluations),
                "unresolved_matches": unresolved,
            },
            request_id=request_id,
        )

    return SourceRunResponse(
        run_id=run_id,
        name=run_name or f"Uploaded CSV control run · {completed_at:%d %b %Y %H:%M UTC}",
        status="COMPLETE",
        source_types=sorted(document.metadata.source_type for _, _, document in documents),
        files_ingested=len(documents),
        events_created=len(events),
        edges_created=len(edges),
        unresolved_matches=unresolved,
        control_evaluations_created=len(evaluations),
        violations_created=sum(item.violation is not None for item in evaluations),
        persistence_status="POSTGRES",
    )


def _validate_bundle(documents: list[tuple[str, str, SourceCsvDocument]]) -> None:
    if not documents:
        raise ValueError("At least one accepted source file is required")
    types = [document.metadata.source_type for _, _, document in documents]
    if "UNRESOLVED" in types:
        raise ValueError("Every file must have a resolved deterministic classification")
    duplicates = sorted({item for item in types if types.count(item) > 1})
    if duplicates:
        raise ValueError(
            "Only one file per source type is allowed in a run: " + ", ".join(duplicates)
        )
    required = {"PAYMENTS", "SETTLEMENTS"}
    missing = sorted(required - set(types))
    if missing:
        raise ValueError("A control run requires: " + ", ".join(missing))


def _canonicalize(
    documents: list[tuple[str, str, SourceCsvDocument]],
    *,
    run_id: str,
    completed_at: datetime,
) -> tuple[list[FinancialEvent], list[CanonicalEventEdge], int]:
    by_type = {document.metadata.source_type: document.rows for _, _, document in documents}
    events: dict[str, FinancialEvent] = {}
    edges: dict[str, CanonicalEventEdge] = {}

    def add_event(
        source_type: str,
        external_id: str,
        event_type: str,
        row: dict[str, str],
        *,
        amount: Decimal,
        timestamp: datetime,
        normalized: dict[str, Any],
    ) -> FinancialEvent:
        event = FinancialEvent(
            id=f"csv:{event_type.lower()}:{external_id}",
            run_id=run_id,
            source="CSV_UPLOAD",
            external_id=external_id,
            event_type=event_type,
            amount=money(amount),
            currency=(row.get("currency") or "INR").upper(),
            timestamp=timestamp,
            status=row.get("status") or row.get("expected_status") or None,
            raw_payload=row,
            normalized_payload={"source_type": source_type, **normalized},
        )
        if event.id in events:
            raise ValueError(f"Duplicate {event_type.lower()} identifier: {external_id}")
        events[event.id] = event
        return event

    for row in by_type.get("ORDERS", []):
        order_id = _required(row, "order_id", "ORDERS")
        add_event(
            "ORDERS",
            order_id,
            "ORDER",
            row,
            amount=_amount(row, "amount"),
            timestamp=_row_timestamp(row, "ORDERS"),
            normalized={"customer_id": row.get("customer_id"), "payment_id": row.get("payment_id")},
        )

    payment_rows = by_type.get("PAYMENTS", [])
    refund_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row in by_type.get("REFUNDS", []):
        refund_totals[_required(row, "payment_id", "REFUNDS")] += _amount(row, "amount")
    for row in payment_rows:
        payment_id = _required(row, "payment_id", "PAYMENTS")
        payment = add_event(
            "PAYMENTS",
            payment_id,
            "PAYMENT",
            row,
            amount=_amount(row, "amount"),
            timestamp=_row_timestamp(row, "PAYMENTS"),
            normalized={
                "order_id": row.get("order_id"),
                "payment_method": row.get("payment_method", "").lower(),
                "method": row.get("payment_method", "").lower(),
                "card_network": row.get("card_network"),
                "card_scope": row.get("card_scope", "").lower(),
                "international": row.get("card_scope", "").lower() == "international",
                "fee": _decimal_text(row.get("fee")),
                "tax": _decimal_text(row.get("tax")),
                "amount_refunded": str(money(refund_totals[payment_id])),
            },
        )
        order_id = row.get("order_id")
        if order_id and f"csv:order:{order_id}" in events:
            _add_edge(edges, run_id, events[f"csv:order:{order_id}"], payment, "PAID_BY")

    for row in by_type.get("REFUNDS", []):
        refund_id = _required(row, "refund_id", "REFUNDS")
        refund = add_event(
            "REFUNDS",
            refund_id,
            "REFUND",
            row,
            amount=_amount(row, "amount"),
            timestamp=_row_timestamp(row, "REFUNDS"),
            normalized={"payment_id": row.get("payment_id"), "fee": "0.00"},
        )
        payment = events.get(f"csv:payment:{row.get('payment_id', '')}")
        if payment is not None:
            _add_edge(edges, run_id, payment, refund, "REFUNDED_BY")

    settlement_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in by_type.get("SETTLEMENTS", []):
        settlement_groups[_required(row, "settlement_id", "SETTLEMENTS")].append(row)
    for settlement_id, rows in settlement_groups.items():
        amount = sum((_amount(row, "net_amount") for row in rows), Decimal("0"))
        timestamp = max(_row_timestamp(row, "SETTLEMENTS") for row in rows)
        settlement = add_event(
            "SETTLEMENTS",
            settlement_id,
            "SETTLEMENT",
            rows[0],
            amount=amount,
            timestamp=timestamp,
            normalized={
                "payment_ids": [row.get("payment_id") for row in rows],
                "row_count": len(rows),
            },
        )
        for row in rows:
            payment = events.get(f"csv:payment:{row.get('payment_id', '')}")
            if payment is not None:
                _add_edge(edges, run_id, payment, settlement, "INCLUDED_IN")

    for row in by_type.get("CHARGEBACKS", []):
        chargeback_id = _required(row, "chargeback_id", "CHARGEBACKS")
        chargeback = add_event(
            "CHARGEBACKS",
            chargeback_id,
            "CHARGEBACK",
            row,
            amount=_amount(row, "amount"),
            timestamp=_row_timestamp(row, "CHARGEBACKS"),
            normalized={"payment_id": row.get("payment_id"), "fee": _decimal_text(row.get("fee"))},
        )
        payment = events.get(f"csv:payment:{row.get('payment_id', '')}")
        if payment is not None:
            _add_edge(edges, run_id, payment, chargeback, "CHARGEBACKED_BY")

    bank_events: list[FinancialEvent] = []
    for row in by_type.get("BANK_RECONCILIATION", []):
        bank_id = _required(row, "bank_txn_id", "BANK_RECONCILIATION")
        credit = _amount(row, "credit")
        debit = _amount(row, "debit")
        bank_events.append(
            add_event(
                "BANK_RECONCILIATION",
                bank_id,
                "BANK_CREDIT" if credit > 0 else "BANK_DEBIT",
                row,
                amount=credit if credit > 0 else debit,
                timestamp=_row_timestamp(row, "BANK_RECONCILIATION"),
                normalized={
                    "reference": row.get("reference"),
                    "description": row.get("description"),
                },
            )
        )

    settlements = [event for event in events.values() if event.event_type == "SETTLEMENT"]
    matched_banks: set[str] = set()
    unresolved = 0
    for settlement in settlements:
        candidates = [
            (_match_score(settlement, bank), bank)
            for bank in bank_events
            if bank.id not in matched_banks and bank.event_type == "BANK_CREDIT"
        ]
        candidates.sort(key=lambda item: (item[0][0], item[1].id), reverse=True)
        best = candidates[0] if candidates else None
        runner_up_score = candidates[1][0][0] if len(candidates) > 1 else Decimal("0")
        if (
            best
            and best[0][0] >= MATCH_THRESHOLD
            and best[0][0] - runner_up_score >= AMBIGUITY_MARGIN
        ):
            score, evidence = best[0]
            bank = best[1]
            matched_banks.add(bank.id)
            exact = evidence["reference_exact"] and evidence["amount_within_tolerance"]
            _add_edge(
                edges,
                run_id,
                settlement,
                bank,
                "CREDITED_AS",
                confidence=score,
                method="EXACT" if exact else "FUZZY",
                evidence=evidence,
            )
        else:
            unresolved += 1
            digest = sha256(f"{run_id}:{settlement.id}:unresolved".encode()).hexdigest()[:20]
            events[f"csv:unresolved:{digest}"] = FinancialEvent(
                id=f"csv:unresolved:{digest}",
                run_id=run_id,
                source="CSV_UPLOAD",
                external_id=f"UNR_{digest[:8].upper()}",
                event_type="UNRESOLVED_MATCH",
                amount=settlement.amount,
                currency=settlement.currency,
                timestamp=completed_at,
                status="unresolved",
                raw_payload={},
                normalized_payload={
                    "settlement_id": settlement.external_id,
                    "threshold": str(MATCH_THRESHOLD),
                    "best_score": str(best[0][0]) if best else "0",
                    "runner_up_score": str(runner_up_score),
                    "candidate_bank_references": [item[1].external_id for item in candidates[:3]],
                    "matching_evidence": best[0][1] if best else {},
                    "decision": "UNRESOLVED",
                    "authority": "DETERMINISTIC",
                },
            )
    return list(events.values()), list(edges.values()), unresolved


def _add_edge(
    edges: dict[str, CanonicalEventEdge],
    run_id: str,
    source: FinancialEvent,
    target: FinancialEvent,
    relationship: str,
    *,
    confidence: Decimal = Decimal("1"),
    method: str = "EXACT",
    evidence: dict[str, Any] | None = None,
) -> None:
    edge_id = f"csv:edge:{relationship.lower()}:{source.external_id}:{target.external_id}"
    edges[edge_id] = CanonicalEventEdge(
        id=edge_id,
        run_id=run_id,
        from_event_id=source.id,
        to_event_id=target.id,
        relationship=relationship,
        confidence=confidence,
        method=method,
        evidence=evidence or {"authority": "DETERMINISTIC", "matched_on": "explicit_reference"},
    )


def _match_score(
    settlement: FinancialEvent, bank: FinancialEvent
) -> tuple[Decimal, dict[str, Any]]:
    reference = str(bank.normalized_payload.get("reference") or "").strip().lower()
    description = str(bank.normalized_payload.get("description") or "").strip().lower()
    needle = settlement.external_id.lower()
    reference_exact = needle == reference or needle in description.split()
    similarity = Decimal(str(SequenceMatcher(None, needle, f"{reference} {description}").ratio()))
    settlement_tokens = set(needle.replace("_", " ").split())
    bank_tokens = set(f"{reference} {description}".replace("_", " ").split())
    overlap = Decimal(len(settlement_tokens & bank_tokens)) / Decimal(
        max(len(settlement_tokens), 1)
    )
    amount_delta = abs(bank.amount - settlement.amount)
    amount_equal = amount_delta <= AMOUNT_TOLERANCE
    days = abs((bank.timestamp - settlement.timestamp).total_seconds()) / 86400
    time_score = Decimal("1") if days <= 3 else Decimal("0.5") if days <= 7 else Decimal("0")
    score = (
        Decimal("0.45") * (Decimal("1") if amount_equal else Decimal("0"))
        + Decimal("0.30") * overlap
        + Decimal("0.15") * similarity
        + Decimal("0.10") * time_score
    )
    score = score.quantize(Decimal("0.0001"))
    return score, {
        "authority": "DETERMINISTIC",
        "reference_exact": reference_exact,
        "reference_token_overlap": str(overlap.quantize(Decimal("0.0001"))),
        "normalized_string_similarity": str(similarity.quantize(Decimal("0.0001"))),
        "amount_difference": str(money(amount_delta)),
        "amount_tolerance": str(AMOUNT_TOLERANCE),
        "amount_within_tolerance": amount_equal,
        "timestamp_distance_days": str(Decimal(str(days)).quantize(Decimal("0.01"))),
        "confidence_score": str(score),
        "threshold": str(MATCH_THRESHOLD),
    }


def _build_root_causes(run_id: str, evaluations: list[LiveControlEvaluation]) -> list[RootCause]:
    groups: dict[str, list[LiveControlEvaluation]] = defaultdict(list)
    for evaluation in evaluations:
        if evaluation.violation is not None:
            groups[evaluation.control.control_type.value].append(evaluation)
    titles = {
        ControlType.MDR_RATE.value: "Systemic MDR rate deviation",
        ControlType.GST_ON_FEE.value: "Systemic GST fee deviation",
        ControlType.SETTLEMENT_SLA.value: "Settlement SLA breach pattern",
        ControlType.REFUND_INTEGRITY.value: "Refund integrity deviation",
        ControlType.SETTLEMENT_ARITHMETIC.value: "Settlement arithmetic mismatch",
    }
    roots = []
    for category, items in sorted(groups.items()):
        violations = [item.violation for item in items if item.violation is not None]
        first = min(item.occurred_at for item in violations)
        last = max(item.occurred_at for item in violations)
        digest = sha256(f"{run_id}:{category}".encode()).hexdigest()[:16].upper()
        downstream = category == ControlType.SETTLEMENT_ARITHMETIC.value
        roots.append(
            RootCause(
                id=f"RC_{digest}",
                title=titles.get(category, category.replace("_", " ").title()),
                category=category,
                affected_count=len(violations),
                verified_impact=money(
                    sum((item.financial_impact for item in violations), Decimal("0"))
                ),
                expected_value=violations[0].expected,
                observed_value=violations[0].actual,
                first_seen=first,
                last_seen=last,
                verification_status="DETERMINISTICALLY_VERIFIED",
                verification_evidence={
                    "engine": "sl3dge-deterministic-v1",
                    "evaluation_ids": [item.evaluation_id for item in items],
                },
                primary_violation_count=0 if downstream else len(violations),
                downstream_effect_count=len(violations) if downstream else 0,
            )
        )
    return roots


def _id_column(source_type: str) -> str:
    return {
        "ORDERS": "order_id",
        "PAYMENTS": "payment_id",
        "REFUNDS": "refund_id",
        "SETTLEMENTS": "settlement_id",
        "CHARGEBACKS": "chargeback_id",
        "BANK_RECONCILIATION": "bank_txn_id",
    }[source_type]


def _required(row: dict[str, str], column: str, source_type: str) -> str:
    value = (row.get(column) or "").strip()
    if not value:
        raise ValueError(f"{source_type} contains an empty {column}")
    return value


def _amount(row: dict[str, str], column: str) -> Decimal:
    raw = (row.get(column) or "0").strip() or "0"
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value in {column}") from exc
    if not value.is_finite():
        raise ValueError(f"Non-finite decimal value in {column}")
    return money(value)


def _decimal_text(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return str(_amount({"value": value}, "value"))


def _row_timestamp(
    row: dict[str, str], source_type: str, *, required: bool = True
) -> datetime | None:
    column = {
        "ORDERS": "created_at",
        "PAYMENTS": "captured_at",
        "REFUNDS": "created_at",
        "SETTLEMENTS": "settled_at",
        "CHARGEBACKS": "created_at",
        "BANK_RECONCILIATION": "posted_at",
    }[source_type]
    raw = (row.get(column) or "").strip()
    if not raw:
        if required:
            raise ValueError(f"{source_type} contains an empty {column}")
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{source_type} contains an invalid ISO-8601 {column}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
