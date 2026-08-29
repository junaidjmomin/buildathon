from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[3]


@dataclass(frozen=True)
class DatasetFixture:
    dataset_id: str
    dataset_type: str
    root: Path
    manifest: dict[str, Any]
    ground_truth: Path | None

    @property
    def source_paths(self) -> dict[str, Path]:
        return {
            "orders": self.root / "orders.csv",
            "payments": self.root / "payments.csv",
            "settlements": self.root / "settlements.csv",
            "bank": self.root / "bank.csv",
            "refunds": self.root / "refunds.csv",
            "chargebacks": self.root / "chargebacks.csv",
        }


def load_dataset_fixture(name: str) -> DatasetFixture:
    roots = {
        "canonical_demo": ROOT / "data" / "demo",
        "prod_stress": ROOT / "data" / "stress",
    }
    if name not in roots:
        raise ValueError(f"Unknown dataset fixture: {name}")
    root = roots[name]
    manifest = json.loads((root / "manifest.json").read_text())
    return DatasetFixture(
        dataset_id=manifest["dataset_id"],
        dataset_type=manifest["dataset_type"],
        root=root,
        manifest=manifest,
        ground_truth=(root / "ground_truth.csv") if (root / "ground_truth.csv").exists() else None,
    )
