from src.standard import PaperInteractionExtraction, SpeciesInteraction


def test_structured_output_schema_requires_nullable_fields() -> None:
    paper_schema = PaperInteractionExtraction.model_json_schema()
    assert set(paper_schema["required"]) == {"evidence_type", "interactions"}
    interaction_schema = paper_schema["$defs"]["SpeciesInteraction"]
    assert set(interaction_schema["required"]) == set(SpeciesInteraction.model_fields)
    assert paper_schema["additionalProperties"] is False
    assert interaction_schema["additionalProperties"] is False


def test_multiple_interactions_validate() -> None:
    result = PaperInteractionExtraction.model_validate(
        {
            "evidence_type": "direct observation",
            "interactions": [
                {
                    "source_taxon_name": "Garrulus glandarius",
                    "interaction_type_name": "eats",
                    "target_taxon_name": "Fagus sylvatica",
                    "part_of_target_taxon": "seed",
                    "time_of_occurrence": None,
                    "locality_name": "Netherlands",
                    "decimal_latitude": None,
                    "decimal_longitude": None,
                    "observation_date_time": "2020-2021",
                    "remarks": None,
                },
                {
                    "source_taxon_name": "Garrulus glandarius",
                    "interaction_type_name": "disperses",
                    "target_taxon_name": "Fagus sylvatica",
                    "part_of_target_taxon": "seed",
                    "time_of_occurrence": "autumn",
                    "locality_name": "Netherlands",
                    "decimal_latitude": None,
                    "decimal_longitude": None,
                    "observation_date_time": "2020-2021",
                    "remarks": None,
                },
            ],
        }
    )
    assert len(result.interactions) == 2
