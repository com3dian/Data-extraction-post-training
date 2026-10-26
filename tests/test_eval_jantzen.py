import csv
from pathlib import Path

import pytest

from src.eval.jantzen import (
    BOTH_MISSING,
    BOTH_PRESENT,
    COORDINATE_TOLERANCE_DEGREES,
    GROUND_TRUTH_ONLY,
    INVERSE_INTERACTIONS,
    UNPAIRED_INTERACTIONS,
    evaluate_run,
    parse_year_set,
    rouge_l_score,
    score_field,
    write_evaluation,
)
from src.standard import InteractionType

GT_HEADERS = [
    "Paper ID",
    "Reference DOI",
    "sourceTaxonName",
    "interactionTypeName",
    "targetTaxonName",
    "PartOfTargetTaxon",
    "timeOfOccurrence",
    "localityName",
    "decimalLatitude",
    "decimalLongitude",
    "observationDateTime",
    "Remarks",
]
PRED_HEADERS = [
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


def test_every_interaction_label_is_reversible_or_explicitly_unpaired() -> None:
    classified = set(INVERSE_INTERACTIONS) | set(UNPAIRED_INTERACTIONS)
    assert classified == {item.value for item in InteractionType}


def test_year_sets_keep_the_whole_range() -> None:
    assert parse_year_set("2016") == {2016}
    assert parse_year_set("2012-2014") == {2012, 2013, 2014}
    assert parse_year_set("2010-14") == {2010, 2011, 2012, 2013, 2014}
    assert parse_year_set("1998-02") == {1998, 1999, 2000, 2001, 2002}
    assert parse_year_set("1959–2013") == set(range(1959, 2014))
    assert 1976 in parse_year_set("1975–1984; 2001–2009")
    assert 2005 in parse_year_set("1975–1984; 2001–2009")
    assert parse_year_set("2012-07-01") == {2012}
    assert parse_year_set("2012-07-01/2013-10-01") == {2012, 2013}
    assert parse_year_set("autumn") is None


def test_year_decision_requires_the_same_set() -> None:
    decision, overlap = score_field("observation_date_time", "2012-2014", "2012")
    assert decision == 0.0
    assert overlap == pytest.approx(1 / 3)
    decision, overlap = score_field("observation_date_time", "2012-2014", "2012–2014")
    assert decision == 1.0
    assert overlap == 1.0


def test_taxon_decision_is_exact_and_keeps_rouge_as_the_soft_score() -> None:
    decision, soft = score_field(
        "source_taxon_name",
        "Apodemus flavicollis",
        "Apodemus sylvaticus",
    )
    assert decision == 0.0
    assert soft == pytest.approx(rouge_l_score("Apodemus flavicollis", "Apodemus sylvaticus"))
    assert soft > 0
    exact, _ = score_field("target_taxon_name", "Fagus sylvatica", "fagus  sylvatica")
    assert exact == 1.0


def test_part_singular_and_coordinates() -> None:
    decision, soft = score_field("part_of_target_taxon", "seeds", "seed")
    assert decision == 1.0
    assert soft < 1.0
    decision, difference = score_field("decimal_latitude", "52,75", "52.75")
    assert decision == 1.0
    assert difference == 0.0
    decision, difference = score_field("decimal_longitude", "25.67", "25.80")
    assert decision == 0.0
    assert difference == pytest.approx(0.13)
    assert difference > COORDINATE_TOLERANCE_DEGREES


def test_locality_reports_containment_separately_from_rouge() -> None:
    decision, contained = score_field(
        "locality_name",
        "Estonia (Jarvamaa; Laane Virumaa)",
        "Estonia",
    )
    assert 0 < decision < 1
    assert contained == 1.0


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _gt(paper_id: str, **fields: str) -> dict[str, str]:
    row = dict.fromkeys(GT_HEADERS, "NA")
    row["Paper ID"] = paper_id
    row["Reference DOI"] = ""
    mapping = {
        "source_taxon_name": "sourceTaxonName",
        "interaction_type_name": "interactionTypeName",
        "target_taxon_name": "targetTaxonName",
        "part_of_target_taxon": "PartOfTargetTaxon",
        "time_of_occurrence": "timeOfOccurrence",
        "locality_name": "localityName",
        "decimal_latitude": "decimalLatitude",
        "decimal_longitude": "decimalLongitude",
        "observation_date_time": "observationDateTime",
        "remarks": "Remarks",
    }
    for field, value in fields.items():
        row[mapping[field]] = value
    return row


def _pred(paper_id: str, index: int, **fields: str) -> dict[str, str]:
    row = dict.fromkeys(PRED_HEADERS, "")
    row["paper_id"] = f"paper_{paper_id}__test"
    row["record_index"] = str(index)
    row["evidence_type"] = fields.pop("evidence_type", "direct observation")
    row.update(fields)
    return row


def _run(
    tmp_path: Path,
    *,
    ground_truth: list[dict[str, str]],
    predictions: dict[str, list[dict[str, str]]],
    evidence: dict[str, str],
):
    _write_csv(tmp_path / "interaction_data.csv", GT_HEADERS, ground_truth)
    paper_rows = [
        {"Paper ID": paper_id, "Type of evidence": value} for paper_id, value in evidence.items()
    ]
    _write_csv(tmp_path / "papers_searched.csv", ["Paper ID", "Type of evidence"], paper_rows)
    for paper_id, rows in predictions.items():
        _write_csv(
            tmp_path / "by_paper" / f"paper_{paper_id}__abcd1234.csv",
            PRED_HEADERS,
            rows,
        )
    return evaluate_run(
        tmp_path,
        tmp_path / "interaction_data.csv",
        tmp_path / "papers_searched.csv",
    )


def _cells(evaluation, paper_id: str, field: str) -> list:
    return [
        cell
        for cell in evaluation.cells
        if cell.paper_id == paper_id and cell.field == field
    ]


def test_reversed_interaction_matches_and_a_wrong_label_stays_wrong(tmp_path: Path) -> None:
    evaluation = _run(
        tmp_path,
        ground_truth=[
            _gt(
                "275",
                source_taxon_name="Myodes glareolus",
                interaction_type_name="has ectoparasite",
                target_taxon_name="Ixodes ricinus",
                locality_name="Estonia (Jarvamaa)",
                decimal_latitude="58.74",
                decimal_longitude="25.67",
                observation_date_time="2012-2014",
            ),
            _gt(
                "10",
                source_taxon_name="Garrulus glandarius",
                interaction_type_name="eats",
                target_taxon_name="Fagus sylvatica",
                part_of_target_taxon="seed",
                locality_name="Netherlands",
                observation_date_time="2018",
            ),
        ],
        predictions={
            "275": [
                _pred(
                    "275",
                    1,
                    source_taxon_name="Ixodes ricinus",
                    interaction_type_name="parasitoid of",
                    target_taxon_name="Myodes glareolus",
                    locality_name="Estonia",
                    observation_date_time="2012-2014",
                )
            ],
            "10": [
                _pred(
                    "10",
                    1,
                    source_taxon_name="Fagus sylvatica",
                    interaction_type_name="is eaten by",
                    target_taxon_name="Garrulus glandarius",
                    part_of_target_taxon="seeds",
                    locality_name="Netherlands",
                    observation_date_time="2018",
                )
            ],
        },
        evidence={"275": "direct observation", "10": "direct observation"},
    )
    source, interaction, target, part = (
        _cells(evaluation, "275", field)[0]
        for field in (
            "source_taxon_name",
            "interaction_type_name",
            "target_taxon_name",
            "part_of_target_taxon",
        )
    )
    assert source.oriented == "1"
    assert source.predicted_value == "Myodes glareolus"
    assert source.decision_score == "1"
    assert target.decision_score == "1"
    assert interaction.predicted_value == "has parasitoid"
    assert interaction.decision_score == "0"
    assert part.outcome == BOTH_MISSING
    latitude = _cells(evaluation, "275", "decimal_latitude")[0]
    assert latitude.outcome == GROUND_TRUTH_ONLY
    assert latitude.decision_score == ""

    eaten = _cells(evaluation, "10", "interaction_type_name")[0]
    assert eaten.oriented == "1"
    assert eaten.decision_score == "1"
    assert _cells(evaluation, "10", "part_of_target_taxon")[0].decision_score == "1"
    remarks = next(row for row in evaluation.field_rows() if row["field"] == "remarks")
    assert remarks["both_missing"] == "2"
    assert remarks["similarity"] == ""


def test_greedy_matches_with_no_score_cutoff(tmp_path: Path) -> None:
    evaluation = _run(
        tmp_path,
        ground_truth=[
            _gt(
                "7",
                source_taxon_name="Myodes glareolus",
                interaction_type_name="has ectoparasite",
                target_taxon_name="Ixodes ricinus",
                locality_name="Estonia",
                observation_date_time="2012-2014",
            )
        ],
        predictions={
            "7": [
                _pred(
                    "7",
                    1,
                    source_taxon_name="Rickettsia",
                    interaction_type_name="pathogen of",
                    target_taxon_name="Homo sapiens",
                    locality_name="Estonia",
                    observation_date_time="2012-2014",
                )
            ]
        },
        evidence={"7": "direct observation"},
    )
    paper = evaluation.papers[0]
    assert paper.n_matched == 1
    assert paper.n_prediction_only == 0
    assert paper.n_ground_truth_only == 0
    assert paper.factual_rate == "1"
    assert paper.retrieval_rate == "1"
    source = _cells(evaluation, "7", "source_taxon_name")[0]
    assert source.outcome == BOTH_PRESENT
    assert source.decision_score == "0"


def test_empty_prediction_counts_ground_truth_rows_as_misses(tmp_path: Path) -> None:
    evaluation = _run(
        tmp_path,
        ground_truth=[
            _gt(
                "3",
                source_taxon_name="Fagus sylvatica",
                interaction_type_name="eats",
                target_taxon_name="Apodemus flavicollis",
            )
        ],
        predictions={"3": []},
        evidence={"3": "correlational"},
    )
    paper = evaluation.papers[0]
    assert paper.n_predicted == 0
    assert paper.n_matched == 0
    assert paper.n_ground_truth_only == 1
    assert paper.factual_rate == ""
    assert paper.retrieval_rate == "0"
    assert paper.evidence_outcome == GROUND_TRUTH_ONLY
    source = _cells(evaluation, "3", "source_taxon_name")
    assert len(source) == 1
    assert source[0].outcome == GROUND_TRUTH_ONLY


def test_one_ground_truth_row_is_not_matched_twice_and_coordinates_can_flag_a_swap(
    tmp_path: Path,
) -> None:
    evaluation = _run(
        tmp_path,
        ground_truth=[
            _gt(
                "4",
                source_taxon_name="Fagus sylvatica",
                interaction_type_name="has habitat",
                target_taxon_name="Quercus robur",
                decimal_latitude="52.10",
                decimal_longitude="5.20",
                remarks="noted in the plot",
            )
        ],
        predictions={
            "4": [
                _pred(
                    "4",
                    1,
                    source_taxon_name="Fagus sylvatica",
                    interaction_type_name="has habitat",
                    target_taxon_name="Quercus robur",
                    decimal_latitude="5.20",
                    decimal_longitude="52.10",
                    remarks="noted in the plot",
                ),
                _pred(
                    "4",
                    2,
                    source_taxon_name="Fagus sylvatica",
                    interaction_type_name="has habitat",
                    target_taxon_name="Quercus robur",
                    remarks="a second copy",
                ),
            ]
        },
        evidence={"4": "direct observation"},
    )
    paper = evaluation.papers[0]
    assert paper.n_matched == 1
    assert paper.n_prediction_only == 1
    assert paper.factual_rate == "0.5"
    latitude = next(
        cell
        for cell in _cells(evaluation, "4", "decimal_latitude")
        if cell.outcome == BOTH_PRESENT
    )
    assert latitude.decision_score == "0"
    assert latitude.coordinate_swap == "1"
    remarks = next(
        cell for cell in _cells(evaluation, "4", "remarks") if cell.outcome == BOTH_PRESENT
    )
    assert remarks.decision_score == "1"


def test_conflicting_evidence_scores_zero(tmp_path: Path) -> None:
    evaluation = _run(
        tmp_path,
        ground_truth=[
            _gt(
                "8",
                source_taxon_name="Fagus sylvatica",
                interaction_type_name="eats",
                target_taxon_name="Apodemus flavicollis",
            )
        ],
        predictions={
            "8": [
                _pred(
                    "8",
                    1,
                    evidence_type="direct observation",
                    source_taxon_name="Fagus sylvatica",
                    interaction_type_name="eats",
                    target_taxon_name="Apodemus flavicollis",
                ),
                _pred(
                    "8",
                    2,
                    evidence_type="correlational",
                    source_taxon_name="Other taxon",
                    interaction_type_name="visits",
                    target_taxon_name="Another taxon",
                ),
            ]
        },
        evidence={"8": "direct observation"},
    )
    evidence = _cells(evaluation, "8", "evidence_type")[0]
    assert evidence.conflict == "1"
    assert evidence.decision_score == "0"
    assert "direct observation" in evidence.predicted_value
    assert "correlational" in evidence.predicted_value
    paths = write_evaluation(evaluation, tmp_path / "eval")
    with paths["fields"].open(encoding="utf-8", newline="") as handle:
        fields = list(csv.DictReader(handle))
    assert [row["field"] for row in fields][-1] == "evidence_type"


ROOT = Path(__file__).resolve().parents[1]
V2_DIR = ROOT / "outputs/zeroshot/jantzen_qwen36_27b_fp8_rules_v2"
INTERACTION_CSV = ROOT / "data/source/Jantzen_species_interaction/interaction_data.csv"
PAPERS_CSV = ROOT / "data/source/Jantzen_species_interaction/papers_searched.csv"


@pytest.mark.skipif(not V2_DIR.exists(), reason="v2 predictions are not in this checkout")
def test_v2_run_keeps_every_predicted_paper() -> None:
    evaluation = evaluate_run(V2_DIR, INTERACTION_CSV, PAPERS_CSV)
    assert len(evaluation.papers) == 94
    empty = [paper for paper in evaluation.papers if paper.n_predicted == 0]
    assert len(empty) == 23
    assert all(paper.n_matched == 0 and paper.retrieval_rate == "0" for paper in empty)
    assert sum(paper.n_ground_truth for paper in evaluation.papers) == 921
    assert sum(paper.n_predicted for paper in evaluation.papers) == 672
    fields = {row["field"]: row for row in evaluation.field_rows()}
    assert int(fields["remarks"]["prediction_only"]) > int(fields["remarks"]["both_present"])
    latitude = fields["decimal_latitude"]
    assert int(latitude["ground_truth_only"]) > int(latitude["both_present"])
