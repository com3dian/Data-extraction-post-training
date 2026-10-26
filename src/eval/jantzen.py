"""Cell-level evaluation of Jantzen species-interaction extractions.

Records are matched inside each paper, then every field is scored on its own.
Matching uses the interaction identity (source, type, target, and part when
either side has one) and may reverse a directional interaction. Pairs are
committed greedily from the highest identity score down, with no cutoff, until
every row on the shorter side has a partner. Locality and year do not affect
that ranking. Both-empty cells are counted and left out of the similarity
average.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

COORDINATE_TOLERANCE_DEGREES = 0.05
MAX_YEAR_SPAN = 150

SOURCE = "source_taxon_name"
INTERACTION = "interaction_type_name"
TARGET = "target_taxon_name"
PART = "part_of_target_taxon"
SEASON = "time_of_occurrence"
LOCALITY = "locality_name"
LATITUDE = "decimal_latitude"
LONGITUDE = "decimal_longitude"
YEARS = "observation_date_time"
REMARKS = "remarks"
EVIDENCE = "evidence_type"

ROW_FIELDS = (
    SOURCE,
    INTERACTION,
    TARGET,
    PART,
    SEASON,
    LOCALITY,
    LATITUDE,
    LONGITUDE,
    YEARS,
    REMARKS,
)
ALL_FIELDS = (*ROW_FIELDS, EVIDENCE)

GT_COLUMNS = {
    SOURCE: "sourceTaxonName",
    INTERACTION: "interactionTypeName",
    TARGET: "targetTaxonName",
    PART: "PartOfTargetTaxon",
    SEASON: "timeOfOccurrence",
    LOCALITY: "localityName",
    LATITUDE: "decimalLatitude",
    LONGITUDE: "decimalLongitude",
    YEARS: "observationDateTime",
    REMARKS: "Remarks",
}

BOTH_PRESENT = "both_present"
PREDICTION_ONLY = "prediction_only"
GROUND_TRUTH_ONLY = "ground_truth_only"
BOTH_MISSING = "both_missing"

CELL_COLUMNS = [
    "paper_id",
    "pred_record_index",
    "gt_row",
    "field",
    "outcome",
    "ground_truth_value",
    "predicted_value",
    "decision_score",
    "soft_score",
    "oriented",
    "coordinate_swap",
    "conflict",
]
FIELD_COLUMNS = [
    "field",
    "both_present",
    "prediction_only",
    "ground_truth_only",
    "both_missing",
    "similarity",
    "factual_rate",
    "retrieval_rate",
]
PAPER_COLUMNS = [
    "paper_id",
    "n_ground_truth",
    "n_predicted",
    "n_matched",
    "n_prediction_only",
    "n_ground_truth_only",
    "factual_rate",
    "retrieval_rate",
    "evidence_outcome",
    "evidence_score",
    "evidence_conflict",
]

_MISSING_TOKENS = frozenset({"", "na", "n/a", "null", "none", "nan", "-", "—", "–"})
_DASH_RE = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212]")
_PAPER_FILE_RE = re.compile(r"^paper_(\d+)__.+\.csv$")
_DATE_RANGE_RE = re.compile(
    r"(?P<start>\d{4})-\d{2}-\d{2}\s*/\s*(?P<end>\d{4})-\d{2}-\d{2}"
)
_YEAR_RANGE_RE = re.compile(r"(?P<start>\d{4})\s*-\s*(?P<end>\d{4})")
_SHORT_RANGE_RE = re.compile(r"(?P<start>\d{4})\s*-\s*(?P<end>\d{2})(?![\d-])")
_YEAR_RE = re.compile(r"(?P<year>\d{4})")
_DEGREES_RE = re.compile(r"[+-]?\d+(?:\.\d+)?")

# Directional labels whose source and target can be swapped. Labels with no
# inverse are omitted: reversing them is not a second valid writing.
_INVERSE_PAIRS = (
    ("eats", "is eaten by"),
    ("acquires nutrients from", "provides nutrients for"),
    ("allelopath of", "has allelopath"),
    ("has vector", "is vector for"),
    ("kills", "is killed by"),
    ("epiphyte of", "has epiphyte"),
    ("host of", "has host"),
    ("hyperparasite of", "hyperparasitized by"),
    ("parasite of", "parasitized by"),
    ("ectoparasite of", "has ectoparasite"),
    ("endoparasite of", "has endoparasite"),
    ("intercellular endoparasite of", "has intercellular endoparasite"),
    ("intracellular endoparasite of", "has intracellular endoparasite"),
    ("lays eggs in", "has eggs laid in by"),
    ("mesoparasite of", "has mesoparasite"),
    ("parasitoid of", "has parasitoid"),
    ("pathogen of", "has pathogen"),
    ("kleptoparasite of", "kleptoparasitized by"),
    ("has reservoir host", "reservoir host of"),
    ("pollinates", "pollinated by"),
    ("preys on", "preyed upon by"),
    ("visits", "visited by"),
    ("lays eggs on", "has eggs laid on by"),
    ("visits flowers of", "has flowers visited by"),
    ("disperses", "is dispersed by"),
)
_SYMMETRIC_INTERACTIONS = frozenset(
    {
        "participates in a abiotic-biotic interaction with",
        "participates in a biotic-biotic interaction with",
        "symbiotically interacts with",
        "commensually interacts with",
        "interacts with via parasite-host interaction",
        "mutualisitcally interacts with",
        "trophically interacts with",
        "symbiotrophically interacts with",
        "ecologically co-occurs with",
        "co-roosts with",
        "in competition with",
    }
)
UNPAIRED_INTERACTIONS = frozenset(
    {
        "facultative parasite of",
        "hemiparasite of",
        "obligate parasite of",
        "root parasite of",
        "stem parasite of",
        "trophic parasite of",
        "creates habitat for",
        "transmitted by",
        "has habitat",
        "has roost",
    }
)


def _inverse_map() -> dict[str, str]:
    inverse: dict[str, str] = {}
    for left, right in _INVERSE_PAIRS:
        inverse[left] = right
        inverse[right] = left
    for label in _SYMMETRIC_INTERACTIONS:
        inverse[label] = label
    return inverse


INVERSE_INTERACTIONS = _inverse_map()


def is_missing(value: Any) -> bool:
    """True for blank cells and the placeholders used in the ground truth."""
    if value is None:
        return True
    return str(value).strip().casefold() in _MISSING_TOKENS


def present_text(value: Any) -> str | None:
    """Return the stripped cell text, or None when the cell is missing."""
    if is_missing(value):
        return None
    return str(value).strip()


def normalize_text(value: str) -> str:
    """Casefold, turn unicode dashes into hyphens, and collapse whitespace."""
    return " ".join(_DASH_RE.sub("-", value).casefold().split())


def display_text(value: Any) -> str:
    text = present_text(value)
    return "" if text is None else text


def format_score(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def rouge_l_score(reference: str, prediction: str) -> float:
    """Character ROUGE-L F1 after the same normalization used for exact text."""
    reference_chars = [char for char in normalize_text(reference) if not char.isspace()]
    prediction_chars = [char for char in normalize_text(prediction) if not char.isspace()]
    if not reference_chars or not prediction_chars:
        return 0.0
    reference_length = len(reference_chars)
    prediction_length = len(prediction_chars)
    lengths = [[0] * (prediction_length + 1) for _ in range(reference_length + 1)]
    for i in range(1, reference_length + 1):
        for j in range(1, prediction_length + 1):
            if reference_chars[i - 1] == prediction_chars[j - 1]:
                lengths[i][j] = lengths[i - 1][j - 1] + 1
            else:
                lengths[i][j] = max(lengths[i - 1][j], lengths[i][j - 1])
    lcs = lengths[reference_length][prediction_length]
    precision = lcs / prediction_length
    recall = lcs / reference_length
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _plural_equivalent(left: str, right: str) -> bool:
    return (
        right in {f"{left}s", f"{left}es"}
        or left in {f"{right}s", f"{right}es"}
    )


def _add_year_span(years: set[int], start: int, end: int) -> None:
    if end < start:
        start, end = end, start
    if end - start > MAX_YEAR_SPAN:
        years.add(start)
        years.add(end)
        return
    years.update(range(start, end + 1))


def parse_year_set(value: str) -> set[int] | None:
    """Parse a year, a closed range, or a slash of full dates into calendar years.

    ``2012-2014`` includes 2013. ``2010-14`` is a two-digit end year. A full
    date such as ``2012-07-01`` contributes only 2012, so the month is not
    read as a second year. Returns None when no year can be read.
    """
    text = _DASH_RE.sub("-", value)
    consumed = [False] * len(text)
    years: set[int] = set()

    def free(match: re.Match[str]) -> bool:
        return not any(consumed[match.start() : match.end()])

    def claim(match: re.Match[str]) -> None:
        for index in range(match.start(), match.end()):
            consumed[index] = True

    for match in _DATE_RANGE_RE.finditer(text):
        if free(match):
            _add_year_span(years, int(match.group("start")), int(match.group("end")))
            claim(match)
    for match in _YEAR_RANGE_RE.finditer(text):
        if free(match):
            _add_year_span(years, int(match.group("start")), int(match.group("end")))
            claim(match)
    for match in _SHORT_RANGE_RE.finditer(text):
        if not free(match):
            continue
        start = int(match.group("start"))
        end = (start // 100) * 100 + int(match.group("end"))
        if end < start:
            end += 100
        _add_year_span(years, start, end)
        claim(match)
    for match in _YEAR_RE.finditer(text):
        if free(match):
            years.add(int(match.group("year")))
            claim(match)
    return years or None


def parse_degrees(value: str) -> float | None:
    """Parse a decimal-degree cell. A comma is a decimal mark, not a thousands separator."""
    text = value.strip().replace(" ", "")
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    if not _DEGREES_RE.fullmatch(text):
        return None
    return float(text)


def _exact(reference: str, prediction: str) -> float:
    return 1.0 if normalize_text(reference) == normalize_text(prediction) else 0.0


def score_field(field: str, reference: str, prediction: str) -> tuple[float, float | None]:
    """Score one cell that is filled on both sides.

    Returns the decision score and the softer companion value. The companion
    is ROUGE-L for taxon names and parts, containment for locality, the
    absolute degree difference for coordinates, and Jaccard overlap for years.
    """
    if field in {SOURCE, TARGET}:
        return _exact(reference, prediction), rouge_l_score(reference, prediction)
    if field == INTERACTION:
        return _exact(reference, prediction), None
    if field == PART:
        rouge = rouge_l_score(reference, prediction)
        left = normalize_text(reference)
        right = normalize_text(prediction)
        decision = 1.0 if left == right or _plural_equivalent(left, right) else rouge
        return decision, rouge
    if field == SEASON:
        if normalize_text(reference) == normalize_text(prediction):
            return 1.0, None
        return rouge_l_score(reference, prediction), None
    if field == LOCALITY:
        prediction_norm = normalize_text(prediction)
        reference_norm = normalize_text(reference)
        contained = 1.0 if prediction_norm and prediction_norm in reference_norm else 0.0
        return rouge_l_score(reference, prediction), contained
    if field in {LATITUDE, LONGITUDE}:
        reference_value = parse_degrees(reference)
        prediction_value = parse_degrees(prediction)
        if reference_value is None or prediction_value is None:
            return 0.0, None
        difference = abs(reference_value - prediction_value)
        decision = 1.0 if difference <= COORDINATE_TOLERANCE_DEGREES else 0.0
        return decision, difference
    if field == YEARS:
        reference_years = parse_year_set(reference)
        prediction_years = parse_year_set(prediction)
        if reference_years is None or prediction_years is None:
            return 0.0, None
        overlap = len(reference_years & prediction_years)
        union = len(reference_years | prediction_years)
        jaccard = overlap / union if union else None
        return (1.0 if reference_years == prediction_years else 0.0), jaccard
    if field == REMARKS:
        return rouge_l_score(reference, prediction), None
    raise KeyError(field)


def _part_identity(reference: str | None, prediction: str | None) -> float | None:
    """Part contribution, or None when both sides are empty so it stays out of the mean."""
    if reference is None and prediction is None:
        return None
    if reference is None or prediction is None:
        return 0.0
    decision, _ = score_field(PART, reference, prediction)
    return decision


def identity_score(
    ground_truth: dict[str, str | None],
    prediction: dict[str, str | None],
) -> float:
    """Mean of source, interaction, and target, plus part when either side has one."""
    components = [
        0.0 if ground_truth[SOURCE] is None or prediction[SOURCE] is None
        else _exact(ground_truth[SOURCE], prediction[SOURCE]),
        0.0 if ground_truth[INTERACTION] is None or prediction[INTERACTION] is None
        else _exact(ground_truth[INTERACTION], prediction[INTERACTION]),
        0.0 if ground_truth[TARGET] is None or prediction[TARGET] is None
        else _exact(ground_truth[TARGET], prediction[TARGET]),
    ]
    part = _part_identity(ground_truth[PART], prediction[PART])
    if part is not None:
        components.append(part)
    return sum(components) / len(components)


def _identity_values(row: dict[str, Any], *, oriented: bool = False) -> dict[str, str | None]:
    source = present_text(row.get(SOURCE))
    target = present_text(row.get(TARGET))
    interaction = present_text(row.get(INTERACTION))
    part = present_text(row.get(PART))
    if oriented:
        source, target = target, source
        if interaction is not None:
            interaction = INVERSE_INTERACTIONS[normalize_text(interaction)]
    return {SOURCE: source, INTERACTION: interaction, TARGET: target, PART: part}


def _can_reverse(row: dict[str, Any]) -> bool:
    interaction = present_text(row.get(INTERACTION))
    return interaction is not None and normalize_text(interaction) in INVERSE_INTERACTIONS


def best_orientation(
    ground_truth: dict[str, Any],
    prediction: dict[str, Any],
) -> tuple[float, bool]:
    """Return the identity score and whether the reversed writing won.

    Equal scores keep the original direction.
    """
    gt_values = _identity_values(ground_truth)
    original = identity_score(gt_values, _identity_values(prediction))
    if not _can_reverse(prediction):
        return original, False
    reversed_score = identity_score(gt_values, _identity_values(prediction, oriented=True))
    if reversed_score > original:
        return reversed_score, True
    return original, False


@dataclass(frozen=True)
class RecordMatch:
    prediction_index: int
    ground_truth_index: int
    oriented: bool
    identity: float


def match_records(
    ground_truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
) -> list[RecordMatch]:
    """Greedy one-to-one matching in descending identity score, with no cutoff."""
    candidates: list[tuple[float, int, int, bool]] = []
    for prediction_index, prediction in enumerate(predictions):
        for ground_truth_index, ground_truth_row in enumerate(ground_truth):
            score, oriented = best_orientation(ground_truth_row, prediction)
            candidates.append((score, prediction_index, ground_truth_index, oriented))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    used_predictions: set[int] = set()
    used_ground_truth: set[int] = set()
    matches: list[RecordMatch] = []
    for score, prediction_index, ground_truth_index, oriented in candidates:
        if prediction_index in used_predictions or ground_truth_index in used_ground_truth:
            continue
        used_predictions.add(prediction_index)
        used_ground_truth.add(ground_truth_index)
        matches.append(
            RecordMatch(prediction_index, ground_truth_index, oriented, score)
        )
    return matches


def _predicted_comparison_value(row: dict[str, Any], field: str, *, oriented: bool) -> str:
    if not oriented or field not in {SOURCE, INTERACTION, TARGET}:
        return display_text(row.get(field))
    values = _identity_values(row, oriented=True)
    return values[field] or ""


def _coordinate_swap(ground_truth: dict[str, Any], prediction: dict[str, Any]) -> bool | None:
    pairs = []
    for field in (LATITUDE, LONGITUDE):
        reference = present_text(ground_truth.get(field))
        predicted = present_text(prediction.get(field))
        if reference is None or predicted is None:
            return None
        reference_value = parse_degrees(reference)
        prediction_value = parse_degrees(predicted)
        if reference_value is None or prediction_value is None:
            return None
        pairs.append((reference_value, prediction_value))
    (gt_lat, pred_lat), (gt_lon, pred_lon) = pairs
    direct = (
        abs(gt_lat - pred_lat) <= COORDINATE_TOLERANCE_DEGREES
        and abs(gt_lon - pred_lon) <= COORDINATE_TOLERANCE_DEGREES
    )
    swapped = (
        abs(gt_lat - pred_lon) <= COORDINATE_TOLERANCE_DEGREES
        and abs(gt_lon - pred_lat) <= COORDINATE_TOLERANCE_DEGREES
    )
    return swapped and not direct


@dataclass(frozen=True)
class CellRecord:
    paper_id: str
    pred_record_index: str
    gt_row: str
    field: str
    outcome: str
    ground_truth_value: str
    predicted_value: str
    decision_score: str = ""
    soft_score: str = ""
    oriented: str = ""
    coordinate_swap: str = ""
    conflict: str = ""

    def as_dict(self) -> dict[str, str]:
        return {column: getattr(self, column) for column in CELL_COLUMNS}


def _score_cell(
    *,
    paper_id: str,
    field: str,
    ground_truth_value: Any,
    predicted_value: str,
    pred_record_index: str,
    gt_row: str,
    oriented: str,
) -> CellRecord:
    reference = display_text(ground_truth_value)
    predicted = predicted_value
    reference_missing = reference == ""
    prediction_missing = predicted == ""
    if reference_missing and prediction_missing:
        outcome = BOTH_MISSING
        decision, soft = "", ""
    elif prediction_missing:
        outcome = GROUND_TRUTH_ONLY
        decision, soft = "", ""
    elif reference_missing:
        outcome = PREDICTION_ONLY
        decision, soft = "", ""
    else:
        outcome = BOTH_PRESENT
        decision_value, soft_value = score_field(field, reference, predicted)
        decision, soft = format_score(decision_value), format_score(soft_value)
    return CellRecord(
        paper_id=paper_id,
        pred_record_index=pred_record_index,
        gt_row=gt_row,
        field=field,
        outcome=outcome,
        ground_truth_value=reference,
        predicted_value=predicted,
        decision_score=decision,
        soft_score=soft,
        oriented=oriented,
    )


def _row_cells(
    *,
    paper_id: str,
    ground_truth: dict[str, Any] | None,
    prediction: dict[str, Any] | None,
    pred_record_index: str,
    gt_row: str,
    oriented: bool,
) -> list[CellRecord]:
    oriented_flag = "1" if oriented else "0"
    cells: list[CellRecord] = []
    for field in ROW_FIELDS:
        reference = "" if ground_truth is None else ground_truth.get(field, "")
        if prediction is None:
            predicted = ""
        else:
            predicted = _predicted_comparison_value(prediction, field, oriented=oriented)
        cell = _score_cell(
            paper_id=paper_id,
            field=field,
            ground_truth_value=reference,
            predicted_value=predicted,
            pred_record_index=pred_record_index,
            gt_row=gt_row,
            oriented=oriented_flag if prediction is not None and ground_truth is not None else "",
        )
        if ground_truth is None or prediction is None:
            if cell.outcome == BOTH_MISSING:
                continue
        cells.append(cell)
    if ground_truth is not None and prediction is not None:
        swap = _coordinate_swap(ground_truth, prediction)
        if swap is not None:
            swapped = "1" if swap else "0"
            cells = [
                replace(cell, coordinate_swap=swapped)
                if cell.field in {LATITUDE, LONGITUDE}
                else cell
                for cell in cells
            ]
    return cells


def _evidence_cell(
    paper_id: str,
    ground_truth: str | None,
    predictions: list[dict[str, Any]],
) -> CellRecord:
    distinct: list[str] = []
    seen: set[str] = set()
    for value in (present_text(row.get(EVIDENCE)) for row in predictions):
        if value is None:
            continue
        key = normalize_text(value)
        if key in seen:
            continue
        seen.add(key)
        distinct.append(value)
    conflict = len(distinct) > 1
    predicted = " | ".join(distinct)
    reference = "" if ground_truth is None else ground_truth
    if reference == "" and predicted == "":
        outcome, decision = BOTH_MISSING, ""
    elif predicted == "":
        outcome, decision = GROUND_TRUTH_ONLY, ""
    elif reference == "":
        outcome, decision = PREDICTION_ONLY, ""
    else:
        outcome = BOTH_PRESENT
        decision = "0" if conflict else format_score(_exact(reference, distinct[0]))
    return CellRecord(
        paper_id=paper_id,
        pred_record_index="",
        gt_row="",
        field=EVIDENCE,
        outcome=outcome,
        ground_truth_value=reference,
        predicted_value=predicted,
        decision_score=decision,
        conflict="1" if conflict else "0",
    )


@dataclass(frozen=True)
class PaperSummary:
    paper_id: str
    n_ground_truth: int
    n_predicted: int
    n_matched: int
    n_prediction_only: int
    n_ground_truth_only: int
    factual_rate: str
    retrieval_rate: str
    evidence_outcome: str
    evidence_score: str
    evidence_conflict: str

    def as_dict(self) -> dict[str, str]:
        return {
            "paper_id": self.paper_id,
            "n_ground_truth": str(self.n_ground_truth),
            "n_predicted": str(self.n_predicted),
            "n_matched": str(self.n_matched),
            "n_prediction_only": str(self.n_prediction_only),
            "n_ground_truth_only": str(self.n_ground_truth_only),
            "factual_rate": self.factual_rate,
            "retrieval_rate": self.retrieval_rate,
            "evidence_outcome": self.evidence_outcome,
            "evidence_score": self.evidence_score,
            "evidence_conflict": self.evidence_conflict,
        }


def _rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return ""
    return format_score(numerator / denominator)


def evaluate_paper(
    paper_id: str,
    ground_truth: list[dict[str, Any]],
    predictions: list[dict[str, Any]],
    evidence_ground_truth: str | None,
) -> tuple[list[CellRecord], PaperSummary]:
    """Match one paper and score every cell, including an empty prediction."""
    matches = match_records(ground_truth, predictions)
    matched_predictions = {match.prediction_index for match in matches}
    matched_ground_truth = {match.ground_truth_index for match in matches}
    cells: list[CellRecord] = []
    for match in sorted(matches, key=lambda item: (item.ground_truth_index, item.prediction_index)):
        prediction = predictions[match.prediction_index]
        cells.extend(
            _row_cells(
                paper_id=paper_id,
                ground_truth=ground_truth[match.ground_truth_index],
                prediction=prediction,
                pred_record_index=str(prediction.get("record_index", match.prediction_index + 1)),
                gt_row=str(match.ground_truth_index + 1),
                oriented=match.oriented,
            )
        )
    for ground_truth_index, ground_truth_row in enumerate(ground_truth):
        if ground_truth_index in matched_ground_truth:
            continue
        cells.extend(
            _row_cells(
                paper_id=paper_id,
                ground_truth=ground_truth_row,
                prediction=None,
                pred_record_index="",
                gt_row=str(ground_truth_index + 1),
                oriented=False,
            )
        )
    for prediction_index, prediction in enumerate(predictions):
        if prediction_index in matched_predictions:
            continue
        cells.extend(
            _row_cells(
                paper_id=paper_id,
                ground_truth=None,
                prediction=prediction,
                pred_record_index=str(prediction.get("record_index", prediction_index + 1)),
                gt_row="",
                oriented=False,
            )
        )
    evidence = _evidence_cell(paper_id, evidence_ground_truth, predictions)
    cells.append(evidence)
    n_prediction_only = len(predictions) - len(matches)
    n_ground_truth_only = len(ground_truth) - len(matches)
    summary = PaperSummary(
        paper_id=paper_id,
        n_ground_truth=len(ground_truth),
        n_predicted=len(predictions),
        n_matched=len(matches),
        n_prediction_only=n_prediction_only,
        n_ground_truth_only=n_ground_truth_only,
        factual_rate=_rate(len(matches), len(matches) + n_prediction_only),
        retrieval_rate=_rate(len(matches), len(matches) + n_ground_truth_only),
        evidence_outcome=evidence.outcome,
        evidence_score=evidence.decision_score,
        evidence_conflict=evidence.conflict,
    )
    return cells, summary


@dataclass(frozen=True)
class Evaluation:
    cells: list[CellRecord]
    papers: list[PaperSummary]

    def field_rows(self) -> list[dict[str, str]]:
        grouped: dict[str, list[CellRecord]] = {field: [] for field in ALL_FIELDS}
        for cell in self.cells:
            grouped.setdefault(cell.field, []).append(cell)
        rows: list[dict[str, str]] = []
        for field in ALL_FIELDS:
            counts = Counter(cell.outcome for cell in grouped[field])
            scored = [
                float(cell.decision_score)
                for cell in grouped[field]
                if cell.outcome == BOTH_PRESENT and cell.decision_score != ""
            ]
            both = counts[BOTH_PRESENT]
            prediction_only = counts[PREDICTION_ONLY]
            ground_truth_only = counts[GROUND_TRUTH_ONLY]
            rows.append(
                {
                    "field": field,
                    "both_present": str(both),
                    "prediction_only": str(prediction_only),
                    "ground_truth_only": str(ground_truth_only),
                    "both_missing": str(counts[BOTH_MISSING]),
                    "similarity": format_score(sum(scored) / len(scored)) if scored else "",
                    "factual_rate": _rate(both, both + prediction_only),
                    "retrieval_rate": _rate(both, both + ground_truth_only),
                }
            )
        return rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _by_paper_dir(prediction_dir: Path) -> Path:
    if prediction_dir.name == "by_paper" and prediction_dir.is_dir():
        return prediction_dir
    candidate = prediction_dir / "by_paper"
    if candidate.is_dir():
        return candidate
    raise FileNotFoundError(f"No by_paper directory in {prediction_dir}")


def _paper_sort_key(paper_id: str) -> tuple[int, int | str]:
    return (0, int(paper_id)) if paper_id.isdigit() else (1, paper_id)


def load_predictions(prediction_dir: Path) -> dict[str, list[dict[str, str]]]:
    """Load per-paper prediction CSVs, including header-only files."""
    grouped: dict[str, list[dict[str, str]]] = {}
    for path in sorted(_by_paper_dir(prediction_dir).glob("*.csv")):
        match = _PAPER_FILE_RE.match(path.name)
        if match is None:
            continue
        paper_id = match.group(1)
        if paper_id in grouped:
            raise ValueError(f"Multiple prediction files for paper {paper_id}")
        rows = _read_csv(path)
        rows.sort(key=lambda row: int(row.get("record_index") or 0))
        grouped[paper_id] = rows
    if not grouped:
        raise FileNotFoundError(f"No paper CSV files in {_by_paper_dir(prediction_dir)}")
    return grouped


def load_ground_truth(
    interaction_csv: Path,
    paper_ids: set[str],
) -> dict[str, list[dict[str, str]]]:
    """Ground-truth interaction rows for the requested papers, in file order."""
    grouped: dict[str, list[dict[str, str]]] = {paper_id: [] for paper_id in paper_ids}
    for row in _read_csv(interaction_csv):
        paper_id = (row.get("Paper ID") or "").strip()
        if paper_id not in grouped:
            continue
        grouped[paper_id].append(
            {field: row.get(column, "") for field, column in GT_COLUMNS.items()}
        )
    missing = sorted(
        (paper_id for paper_id, rows in grouped.items() if not rows),
        key=_paper_sort_key,
    )
    if missing:
        raise ValueError(f"No ground-truth rows for paper IDs: {', '.join(missing)}")
    return grouped


def load_evidence(papers_csv: Path, paper_ids: set[str]) -> dict[str, str | None]:
    evidence: dict[str, str | None] = dict.fromkeys(paper_ids)
    for row in _read_csv(papers_csv):
        paper_id = (row.get("Paper ID") or "").strip()
        if paper_id not in evidence or evidence[paper_id] is not None:
            continue
        evidence[paper_id] = present_text(row.get("Type of evidence"))
    return evidence


def evaluate_run(
    prediction_dir: Path,
    interaction_csv: Path,
    papers_csv: Path,
) -> Evaluation:
    """Evaluate every paper CSV in a zeroshot run against the Jantzen tables."""
    predictions = load_predictions(prediction_dir)
    paper_ids = set(predictions)
    ground_truth = load_ground_truth(interaction_csv, paper_ids)
    evidence = load_evidence(papers_csv, paper_ids)
    cells: list[CellRecord] = []
    papers: list[PaperSummary] = []
    for paper_id in sorted(paper_ids, key=_paper_sort_key):
        paper_cells, summary = evaluate_paper(
            paper_id,
            ground_truth[paper_id],
            predictions[paper_id],
            evidence[paper_id],
        )
        cells.extend(paper_cells)
        papers.append(summary)
    return Evaluation(cells, papers)


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_evaluation(evaluation: Evaluation, output_dir: Path) -> dict[str, Path]:
    """Write cells.csv, fields.csv, and papers.csv."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "cells": output_dir / "cells.csv",
        "fields": output_dir / "fields.csv",
        "papers": output_dir / "papers.csv",
    }
    _write_csv(paths["cells"], CELL_COLUMNS, [cell.as_dict() for cell in evaluation.cells])
    _write_csv(paths["fields"], FIELD_COLUMNS, evaluation.field_rows())
    _write_csv(paths["papers"], PAPER_COLUMNS, [paper.as_dict() for paper in evaluation.papers])
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate a Jantzen zeroshot run cell by cell.")
    parser.add_argument("prediction_dir", type=Path, help="Run directory containing by_paper/")
    parser.add_argument("--interaction-csv", type=Path, required=True)
    parser.add_argument("--papers-csv", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Defaults to <prediction_dir>/eval",
    )
    args = parser.parse_args(argv)
    output_dir = args.output_dir or (args.prediction_dir / "eval")
    evaluation = evaluate_run(args.prediction_dir, args.interaction_csv, args.papers_csv)
    paths = write_evaluation(evaluation, output_dir)
    for row in evaluation.field_rows():
        print(
            f"{row['field']:<24} both={row['both_present']:>5} "
            f"pred_only={row['prediction_only']:>5} gt_only={row['ground_truth_only']:>5} "
            f"similarity={row['similarity'] or '—':>8} "
            f"factual={row['factual_rate'] or '—':>8} "
            f"retrieval={row['retrieval_rate'] or '—':>8}"
        )
    print(f"Wrote {paths['cells']}")
    print(f"Wrote {paths['fields']}")
    print(f"Wrote {paths['papers']}")


if __name__ == "__main__":
    main()
