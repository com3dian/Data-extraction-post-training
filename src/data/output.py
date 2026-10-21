"""Resumable, table-oriented extraction output."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from src.standard import PaperInteractionExtraction

RECORD_COLUMNS = [
    "paper_id",
    "paper_path",
    "record_index",
    "evidence_type",
    "source_taxon_name",
    "interaction_type_name",
    "target_taxon_name",
    "part_of_target_taxon",
    "time_of_occurrence",
    "locality_name",
    "decimal_latitude",
    "decimal_longitude",
    "observation_date_time",
    "remarks",
]

STATUS_COLUMNS = [
    "paper_id",
    "paper_path",
    "provider",
    "model",
    "status",
    "record_count",
    "error",
]


def paper_id(path: Path) -> str:
    """Create a readable, collision-resistant ID from a paper path."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("-_") or "paper"
    digest = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:8]
    return f"{stem}__{digest}"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _atomic_write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="", dir=path.parent, delete=False
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def result_rows(
    result: PaperInteractionExtraction,
    *,
    identifier: str,
    source_path: Path,
) -> list[dict[str, Any]]:
    """Flatten a paper result into one table row per interaction."""
    evidence_type = result.evidence_type.value if result.evidence_type else None
    rows: list[dict[str, Any]] = []
    for index, interaction in enumerate(result.interactions, start=1):
        row = interaction.model_dump(mode="json")
        rows.append(
            {
                "paper_id": identifier,
                "paper_path": str(source_path),
                "record_index": index,
                "evidence_type": evidence_type,
                **row,
            }
        )
    return rows


class ExtractionOutput:
    """Write per-paper checkpoints and rebuild the combined records table."""

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir.resolve()
        self.by_paper_dir = self.run_dir / "by_paper"
        self.raw_dir = self.run_dir / "raw"
        self.status_path = self.run_dir / "run_status.csv"
        self.records_path = self.run_dir / "records.csv"
        self.by_paper_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def is_complete(self, identifier: str) -> bool:
        return (self.by_paper_dir / f"{identifier}.csv").is_file() and (
            self.raw_dir / f"{identifier}.json"
        ).is_file()

    def record_count(self, identifier: str) -> int:
        """Return the number of saved interaction rows for one completed paper."""
        csv_path = self.by_paper_dir / f"{identifier}.csv"
        with csv_path.open(encoding="utf-8", newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))

    def save_result(
        self,
        result: PaperInteractionExtraction,
        *,
        identifier: str,
        source_path: Path,
    ) -> int:
        rows = result_rows(result, identifier=identifier, source_path=source_path)
        _atomic_write_text(
            self.raw_dir / f"{identifier}.json",
            result.model_dump_json(indent=2),
        )
        _atomic_write_csv(
            self.by_paper_dir / f"{identifier}.csv",
            rows,
            RECORD_COLUMNS,
        )
        return len(rows)

    def rebuild_records(self) -> Path:
        rows: list[dict[str, Any]] = []
        for csv_path in sorted(self.by_paper_dir.glob("*.csv")):
            with csv_path.open(encoding="utf-8", newline="") as handle:
                rows.extend(csv.DictReader(handle))
        _atomic_write_csv(self.records_path, rows, RECORD_COLUMNS)
        return self.records_path

    def update_status(self, row: dict[str, Any]) -> None:
        existing: dict[str, dict[str, Any]] = {}
        if self.status_path.is_file():
            with self.status_path.open(encoding="utf-8", newline="") as handle:
                existing = {item["paper_id"]: item for item in csv.DictReader(handle)}
        existing[str(row["paper_id"])] = row
        ordered = [existing[key] for key in sorted(existing)]
        _atomic_write_csv(self.status_path, ordered, STATUS_COLUMNS)

    def write_config(self, config: dict[str, Any]) -> None:
        config_path = self.run_dir / "config.json"
        if config_path.is_file():
            existing = json.loads(config_path.read_text(encoding="utf-8"))
            if existing != config:
                raise ValueError(
                    f"{self.run_dir} already contains a different run configuration; "
                    "use a new --output-dir"
                )
            return
        _atomic_write_text(
            config_path,
            json.dumps(config, indent=2, sort_keys=True),
        )
