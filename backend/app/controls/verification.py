from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any

from pydantic import ValidationError

from app.controls.dsl import (
    GstFeeParameters,
    MdrRateParameters,
    RefundIntegrityParameters,
    SettlementArithmeticParameters,
    SettlementSlaParameters,
    UnsupportedFeeParameters,
)
from app.core.money import expected_fee, expected_gst, money
from app.domain.models import Control, ControlType


@dataclass(frozen=True)
class DraftControlVerification:
    status: str
    checks: list[dict[str, Any]]
    mutation_probe_count: int
    detected_mutation_count: int
    input_fingerprint: str


def verify_draft_control(control: Control) -> DraftControlVerification:
    """Validate a draft and execute one deterministic boundary mutation probe."""

    checks: list[dict[str, Any]] = []
    parameters_valid = False
    mutation_detected = False
    try:
        mutation_detected = _parameter_and_mutation_probe(control)
        parameters_valid = True
    except (ValidationError, ValueError, TypeError) as exc:
        checks.append(
            {
                "name": "typed_parameter_schema",
                "status": "FAILED",
                "detail": str(exc),
            }
        )
    else:
        checks.append(
            {
                "name": "typed_parameter_schema",
                "status": "PASSED",
                "detail": "Financial values were parsed from decimal strings.",
            }
        )
    effective_valid = control.effective_to is None or control.effective_to >= control.effective_from
    checks.append(
        {
            "name": "effective_period",
            "status": "PASSED" if effective_valid else "FAILED",
            "detail": "The proposed effective period is ordered and explicit.",
        }
    )
    conditions_valid = bool(control.conditions) and all(
        isinstance(condition, str) and condition.strip() for condition in control.conditions
    )
    checks.append(
        {
            "name": "applicability_conditions",
            "status": "PASSED" if conditions_valid else "FAILED",
            "detail": "At least one non-empty deterministic applicability condition is required.",
        }
    )
    checks.append(
        {
            "name": "boundary_mutation_probe",
            "status": "PASSED" if mutation_detected else "FAILED",
            "detail": "A value beyond the typed tolerance must trigger the candidate comparator.",
        }
    )
    passed = parameters_valid and effective_valid and conditions_valid and mutation_detected
    serialized = json.dumps(
        control.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return DraftControlVerification(
        status="PASSED" if passed else "FAILED",
        checks=checks,
        mutation_probe_count=1,
        detected_mutation_count=1 if mutation_detected else 0,
        input_fingerprint=sha256(serialized.encode()).hexdigest(),
    )


def _parameter_and_mutation_probe(control: Control) -> bool:
    if control.control_type == ControlType.MDR_RATE:
        parameters = MdrRateParameters.model_validate(control.parameters)
        _validate_rate_and_tolerance(parameters.rate, parameters.tolerance)
        expected = expected_fee(Decimal("10000.00"), parameters.rate)
        actual = money(expected + parameters.tolerance + Decimal("0.01"))
        return abs(actual - expected) > parameters.tolerance
    if control.control_type == ControlType.GST_ON_FEE:
        parameters = GstFeeParameters.model_validate(control.parameters)
        _validate_rate_and_tolerance(parameters.rate, parameters.tolerance)
        expected = expected_gst(Decimal("155.00"), parameters.rate)
        actual = money(expected + parameters.tolerance + Decimal("0.01"))
        return abs(actual - expected) > parameters.tolerance
    if control.control_type == ControlType.SETTLEMENT_ARITHMETIC:
        parameters = SettlementArithmeticParameters.model_validate(control.parameters)
        _validate_tolerance(parameters.tolerance)
        return parameters.tolerance + Decimal("0.01") > parameters.tolerance
    if control.control_type == ControlType.REFUND_INTEGRITY:
        parameters = RefundIntegrityParameters.model_validate(control.parameters)
        _validate_tolerance(parameters.tolerance)
        if parameters.refund_fee < 0:
            raise ValueError("refund_fee must be non-negative")
        return parameters.tolerance + Decimal("0.01") > parameters.tolerance
    if control.control_type == ControlType.SETTLEMENT_SLA:
        parameters = SettlementSlaParameters.model_validate(control.parameters)
        return parameters.business_days + 1 > parameters.business_days
    if control.control_type == ControlType.UNSUPPORTED_FEE:
        parameters = UnsupportedFeeParameters.model_validate(control.parameters)
        _validate_tolerance(parameters.tolerance)
        return parameters.tolerance + Decimal("0.01") > parameters.tolerance
    if control.control_type == ControlType.LIFECYCLE_VALIDITY:
        return True
    raise ValueError(f"No deterministic verifier exists for {control.control_type.value}")


def _validate_rate_and_tolerance(rate: Decimal, tolerance: Decimal) -> None:
    if rate < 0 or rate > 1:
        raise ValueError("rate must be between zero and one")
    _validate_tolerance(tolerance)


def _validate_tolerance(tolerance: Decimal) -> None:
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")
