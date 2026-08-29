"""Execute a labeled CSV bundle through the real API and read back what persisted.

Nothing here knows about labels. The runner drives the same public endpoints the
browser drives, then reads the durable records, so an evaluation can only score
what the product actually produced and stored.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.router import DEMO_TENANT_ID
from app.core.config import get_settings
from app.main import app
from app.persistence.database import get_engine, get_session_factory, session_scope
from app.persistence.orm import (
    Base,
    ControlEvaluationRecord,
    EventEdgeRecord,
    EventRecord,
)
from app.storage.supabase import StoredObject
from tests.support.scoring import Observation

SourceFile = tuple[str, bytes, str]

api_router = import_module("app.api.router")


class _Storage:
    """Deterministic storage double that returns true content hashes."""

    configured = True

    def __init__(self, settings: Any = None) -> None:
        pass

    async def upload(
        self,
        object_path: str,
        content: bytes,
        *,
        content_type: str,
        overwrite: bool = False,
    ) -> StoredObject:
        return StoredObject(
            bucket="private",
            object_path=object_path,
            content_type=content_type,
            byte_size=len(content),
            sha256=sha256(content).hexdigest(),
        )

    async def delete(self, _object_path: str) -> None:
        raise AssertionError("A successful source upload must never be deleted")


@contextmanager
def api_client(database_path: Path) -> Iterator[TestClient]:
    """A client bound to a scratch database, safe for any fixture scope."""

    patch = pytest.MonkeyPatch()
    patch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    # Keep the evaluation hermetic and deterministic.  Production uses OIDC,
    # but these tests intentionally exercise the domain through the API without
    # requiring a live identity provider.
    patch.setenv("AUTH_MODE", "disabled")
    patch.setenv("ENVIRONMENT", "test")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = get_engine()
    assert engine is not None
    Base.metadata.create_all(engine)
    patch.setattr(api_router, "SupabaseStorage", _Storage)
    try:
        # The repository's development environment intentionally allows
        # localhost/127.0.0.1 only.  Starlette's TestClient defaults to the
        # synthetic ``testserver`` host, which is rejected by the same trusted
        # host middleware used in production.  Exercise the public API through
        # an allowed local origin so these tests match browser behaviour.
        yield TestClient(app, base_url="http://localhost")
    finally:
        patch.undo()
        get_session_factory.cache_clear()
        get_engine.cache_clear()
        get_settings.cache_clear()


def read_bundle(paths: dict[str, Path]) -> list[SourceFile]:
    return [(path.name, path.read_bytes(), "text/csv") for path in paths.values()]


def execute_bundle(
    client: TestClient,
    files: list[SourceFile],
    *,
    name: str,
    dataset_id: str | None = None,
    dataset_type: str | None = None,
) -> str:
    """Upload, then execute — the same two calls the browser makes."""

    uploaded = client.post(
        "/api/v1/sources/uploads",
        files=[("files", item) for item in files],
    )
    assert uploaded.status_code == 200, uploaded.text
    upload_ids = [item["upload_id"] for item in uploaded.json()["files"]]
    # Plain form fields ride alongside file parts as (None, value, None) entries;
    # httpx 0.27 cannot mix list-form `data` with `files`.
    parts: list[tuple[str, Any]] = [("name", (None, name, None))]
    if dataset_id is not None:
        parts.append(("dataset_id", (None, dataset_id, None)))
    if dataset_type is not None:
        parts.append(("dataset_type", (None, dataset_type, None)))
    parts.extend(("upload_ids", (None, upload_id, None)) for upload_id in upload_ids)
    parts.extend(("files", item) for item in files)
    created = client.post("/api/v1/runs/from-uploads", files=parts)
    assert created.status_code == 201, created.text
    return created.json()["run_id"]


def _persisted(run_id: str) -> tuple[list[dict[str, Any]], frozenset[str]]:
    """Control evaluations and the settlements that received a bank credit."""

    with session_scope(tenant_id=DEMO_TENANT_ID) as session:
        evaluations = [
            {
                "id": record.id,
                "control_id": record.control_id,
                "control_version": record.control_version,
                "target_type": record.target_type,
                "target_id": record.target_id,
                "check_name": record.check_name,
                "outcome": record.outcome,
                "expected_amount": record.expected_amount,
                "actual_amount": record.actual_amount,
                "tolerance_amount": record.tolerance_amount,
                "difference_amount": record.difference_amount,
                "financial_impact": record.financial_impact,
                "confidence": record.confidence,
                "evidence": record.evidence,
            }
            for record in session.scalars(
                select(ControlEvaluationRecord).where(ControlEvaluationRecord.run_id == run_id)
            )
        ]
        external_by_event = {
            record.id: record.external_id
            for record in session.scalars(select(EventRecord).where(EventRecord.run_id == run_id))
        }
        credited = frozenset(
            external_by_event[record.from_event_id]
            for record in session.scalars(
                select(EventEdgeRecord).where(
                    EventEdgeRecord.run_id == run_id,
                    EventEdgeRecord.relationship == "CREDITED_AS",
                )
            )
            if record.from_event_id in external_by_event
        )
    return evaluations, credited


def observe(client: TestClient, run_id: str, *, dataset_id: str, dataset_type: str) -> Observation:
    """Read every authoritative run view the product publishes."""

    def get(path: str) -> Any:
        response = client.get(f"/api/v1/runs/{run_id}{path}")
        assert response.status_code == 200, response.text
        return response.json()

    controls = client.get("/api/v1/controls")
    assert controls.status_code == 200, controls.text
    evaluations, credited = _persisted(run_id)
    return Observation(
        run_id=run_id,
        dataset_id=dataset_id,
        dataset_type=dataset_type,
        summary=get("/summary"),
        violations=tuple(get("/violations")),
        unresolved=tuple(get("/unresolved")),
        root_causes=tuple(get("/root-causes")),
        evaluations=tuple(evaluations),
        controls=tuple(controls.json()),
        credited_settlement_ids=credited,
    )


# --------------------------------------------------------------------------- #
# Genericity transforms
# --------------------------------------------------------------------------- #


def rename_identifiers(files: list[SourceFile]) -> tuple[list[SourceFile], dict[str, str]]:
    """Rename every identifier consistently across the whole bundle.

    Identifiers are discovered from the data, not from a known prefix list: any
    token that is not a number, date, currency code or lifecycle word is treated
    as an identifier. A prefix allowlist would silently skip the identifiers it
    does not know about, which is exactly what this invariance must catch.
    """

    reserved = {
        "card",
        "upi",
        "netbanking",
        "wallet",
        "domestic",
        "international",
        "captured",
        "failed",
        "authorized",
        "refunded",
        "processed",
        "pending",
        "open",
        "closed",
        "won",
        "lost",
        "paid",
        "created",
        "inr",
        "visa",
        "mastercard",
        "rupay",
        "amex",
    }

    def is_identifier(token: str) -> bool:
        if "_" not in token:
            return False
        if token.lower() in reserved:
            return False
        head, _, tail = token.partition("_")
        return head.isalpha() and head.isupper() and bool(tail)

    discovered: list[str] = []
    seen: set[str] = set()
    for _filename, content, _mime in files:
        for line in content.decode().splitlines():
            for cell in line.split(","):
                token = cell.strip()
                if is_identifier(token) and token not in seen:
                    seen.add(token)
                    discovered.append(token)
    # Longest first, so a shorter identifier can never rewrite a prefix of a
    # longer one during textual substitution.
    mapping = {
        token: f"GEN{index:07d}_X" for index, token in enumerate(sorted(discovered, key=len))
    }
    ordered = sorted(mapping, key=len, reverse=True)
    renamed: list[SourceFile] = []
    for filename, content, mime in files:
        text = content.decode()
        for token in ordered:
            text = text.replace(token, mapping[token])
        renamed.append((filename, text.encode(), mime))
    return renamed, mapping


def shuffle_rows(files: list[SourceFile], *, seed: int) -> list[SourceFile]:
    """Independently shuffle the data rows of every source file."""

    generator = random.Random(seed)
    shuffled: list[SourceFile] = []
    for filename, content, mime in files:
        text = content.decode()
        trailing_newline = text.endswith("\n")
        lines = text.splitlines()
        header, rows = lines[0], lines[1:]
        generator.shuffle(rows)
        body = "\n".join([header, *rows]) + ("\n" if trailing_newline else "")
        shuffled.append((filename, body.encode(), mime))
    return shuffled


#: Run-level fields that are provenance, never business logic. Two runs of the
#: same bytes differ in exactly these and in nothing financial.
PROVENANCE_FIELDS = frozenset(
    {
        "id",
        "name",
        "created_at",
        "completed_at",
        "started_at",
        "deterministic_processing_ms",
        "persistence_ms",
        "total_processing_ms",
        "evaluations_per_second",
        "engine_processing_ms",
    }
)


def financial_conclusions(
    observation: Observation, *, rename: dict[str, str] | None = None
) -> dict[str, Any]:
    """The conclusions that must not move when only provenance changes.

    ``rename`` applies a known identifier bijection to every entity identifier
    before comparison. Comparing under the bijection is stricter than dropping
    identifiers altogether: it proves the conclusions are the *same* conclusions
    about the *same* entities, not merely the same shape and totals.
    """

    translate = (rename or {}).get

    def entity(value: str) -> str:
        return translate(value, value)

    summary = observation.summary
    violations = sorted(
        (
            violation["target_type"],
            entity(violation["payment_id"]),
            violation["violation_type"],
            violation["lineage_type"],
            str(violation["financial_impact"]),
            str(violation["difference"]),
        )
        for violation in observation.violations
    )
    roots = sorted(
        (
            root["category"],
            root["affected_count"],
            root["primary_violation_count"],
            root["downstream_effect_count"],
            str(root["total_attributable_impact"]),
        )
        for root in observation.root_causes
    )
    evaluations = sorted(
        (
            evaluation["control_id"],
            evaluation["target_type"],
            entity(evaluation["target_id"]),
            evaluation["check_name"],
            evaluation["outcome"],
        )
        for evaluation in observation.evaluations
    )
    unresolved = sorted(
        (entity(item["payment_id"]), str(item["amount"])) for item in observation.unresolved
    )
    return {
        "transaction_count": summary["transaction_count"],
        "event_count": summary["event_count"],
        "relationship_count": summary["relationship_count"],
        "control_evaluation_count": summary["control_evaluation_count"],
        "breakdown": summary["breakdown"],
        "primary_violation_count": summary["primary_violation_count"],
        "downstream_violation_count": summary["downstream_violation_count"],
        "unresolved_control_count": summary["unresolved_control_count"],
        "unresolved_relationship_count": summary["unresolved_relationship_count"],
        "verified_leakage": str(summary["verified_leakage"]),
        "cash_delayed": str(summary["cash_delayed"]),
        "violations": violations,
        "root_causes": roots,
        "control_evaluations": evaluations,
        "unresolved_relationships": unresolved,
        "credited_settlements": sorted(
            entity(value) for value in observation.credited_settlement_ids
        ),
    }
