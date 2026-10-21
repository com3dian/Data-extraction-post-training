import csv
import json
from pathlib import Path

from src.data.output import ExtractionOutput, result_rows
from src.standard import PaperInteractionExtraction


def example_result() -> PaperInteractionExtraction:
    return PaperInteractionExtraction.model_validate(
        {
            "evidence_type": "correlational",
            "interactions": [
                {
                    "source_taxon_name": "Fagus sylvatica",
                    "interaction_type_name": "is eaten by",
                    "target_taxon_name": "Apodemus sylvaticus",
                    "part_of_target_taxon": "seed",
                    "time_of_occurrence": "autumn",
                    "locality_name": "Veluwe, Netherlands",
                    "decimal_latitude": 52.2,
                    "decimal_longitude": 5.8,
                    "observation_date_time": "2018-2020",
                    "remarks": "Population-level association",
                },
                {
                    "source_taxon_name": "Apodemus sylvaticus",
                    "interaction_type_name": "disperses",
                    "target_taxon_name": "Fagus sylvatica",
                    "part_of_target_taxon": "seed",
                    "time_of_occurrence": None,
                    "locality_name": "Veluwe, Netherlands",
                    "decimal_latitude": None,
                    "decimal_longitude": None,
                    "observation_date_time": "2018-2020",
                    "remarks": None,
                },
            ],
        }
    )


def test_result_rows_are_one_row_per_interaction(tmp_path: Path) -> None:
    rows = result_rows(example_result(), identifier="paper-1", source_path=tmp_path / "paper.pdf")
    assert len(rows) == 2
    assert rows[0]["record_index"] == 1
    assert rows[1]["interaction_type_name"] == "disperses"
    assert rows[0]["evidence_type"] == "correlational"


def test_output_checkpoints_and_rebuilds_combined_csv(tmp_path: Path) -> None:
    output = ExtractionOutput(tmp_path / "run")
    count = output.save_result(
        example_result(),
        identifier="paper-1",
        source_path=tmp_path / "paper.pdf",
    )
    assert count == 2
    assert output.is_complete("paper-1")
    assert output.record_count("paper-1") == 2
    raw = json.loads((output.raw_dir / "paper-1.json").read_text())
    assert len(raw["interactions"]) == 2

    records_path = output.rebuild_records()
    with records_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]["paper_id"] == "paper-1"


def test_run_config_cannot_be_silently_changed(tmp_path: Path) -> None:
    output = ExtractionOutput(tmp_path / "run")
    output.write_config({"provider": "cliproxy", "model": "gpt-6-luna"})
    output.write_config({"provider": "cliproxy", "model": "gpt-6-luna"})

    try:
        output.write_config({"provider": "surf", "model": "openai/gpt-oss-120b"})
    except ValueError as exc:
        assert "different run configuration" in str(exc)
    else:
        raise AssertionError("A mixed-provider run should have been rejected")
