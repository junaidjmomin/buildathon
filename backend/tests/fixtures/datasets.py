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
    evaluation_files: dict[str, Path]

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
        # Keep the stable 60-row proof fixture beside the tests.  The generated
        # 500-row demo dataset remains an application/demo asset, while these
        # source files are the explicit fixture for exact canonical assertions.
        "canonical_demo": ROOT / "backend" / "tests" / "fixtures" / "canonical_demo",
        "prod_stress": ROOT / "data" / "stress",
        "clause_driven": ROOT / "docs",
    }
    if name not in roots:
        raise ValueError(f"Unknown dataset fixture: {name}")
    root = roots[name]
    manifest = json.loads((root / "manifest.json").read_text())
    evaluation_files = {
        name: root / name
        for name in (
            "ground_truth.csv",
            "relationship_ground_truth.csv",
            "settlement_ground_truth.csv",
            "clause_coverage.csv",
        )
        if (root / name).exists()
    }
    return DatasetFixture(
        dataset_id=manifest["dataset_id"],
        dataset_type=manifest["dataset_type"],
        root=root,
        manifest=manifest,
        ground_truth=(root / "ground_truth.csv") if (root / "ground_truth.csv").exists() else None,
        evaluation_files=evaluation_files,
    )
