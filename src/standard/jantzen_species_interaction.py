"""Pydantic models for extracting Jantzen species interactions from papers.

The models intentionally contain only information that can be supported by the
paper itself. Internal paper IDs, DOI bookkeeping, accepted-name validation,
GBIF identifiers, and ontology IRIs belong to later enrichment steps.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class InteractionType(StrEnum):
    """Controlled interaction vocabulary used by the Jantzen standard."""

    EATS = "eats"
    ACQUIRES_NUTRIENTS_FROM = "acquires nutrients from"
    IS_EATEN_BY = "is eaten by"
    ABIOTIC_BIOTIC_INTERACTION = "participates in a abiotic-biotic interaction with"
    BIOTIC_BIOTIC_INTERACTION = "participates in a biotic-biotic interaction with"
    ALLELOPATH_OF = "allelopath of"
    HAS_ALLELOPATH = "has allelopath"
    HAS_VECTOR = "has vector"
    IS_KILLED_BY = "is killed by"
    IS_VECTOR_FOR = "is vector for"
    KILLS = "kills"
    SYMBIOTICALLY_INTERACTS_WITH = "symbiotically interacts with"
    COMMENSUALLY_INTERACTS_WITH = "commensually interacts with"
    EPIPHYTE_OF = "epiphyte of"
    HAS_EPIPHYTE = "has epiphyte"
    HAS_HOST = "has host"
    HAS_RESERVOIR_HOST = "has reservoir host"
    HYPERPARASITE_OF = "hyperparasite of"
    PARASITE_OF = "parasite of"
    ECTOPARASITE_OF = "ectoparasite of"
    ENDOPARASITE_OF = "endoparasite of"
    INTERCELLULAR_ENDOPARASITE_OF = "intercellular endoparasite of"
    INTRACELLULAR_ENDOPARASITE_OF = "intracellular endoparasite of"
    FACULTATIVE_PARASITE_OF = "facultative parasite of"
    HEMIPARASITE_OF = "hemiparasite of"
    KLEPTOPARASITE_OF = "kleptoparasite of"
    LAYS_EGGS_IN = "lays eggs in"
    MESOPARASITE_OF = "mesoparasite of"
    OBLIGATE_PARASITE_OF = "obligate parasite of"
    PARASITOID_OF = "parasitoid of"
    ROOT_PARASITE_OF = "root parasite of"
    STEM_PARASITE_OF = "stem parasite of"
    PATHOGEN_OF = "pathogen of"
    HOST_OF = "host of"
    HAS_PATHOGEN = "has pathogen"
    HYPERPARASITIZED_BY = "hyperparasitized by"
    PARASITIZED_BY = "parasitized by"
    HAS_ECTOPARASITE = "has ectoparasite"
    HAS_EGGS_LAID_IN_BY = "has eggs laid in by"
    HAS_ENDOPARASITE = "has endoparasite"
    HAS_INTERCELLULAR_ENDOPARASITE = "has intercellular endoparasite"
    HAS_INTRACELLULAR_ENDOPARASITE = "has intracellular endoparasite"
    HAS_MESOPARASITE = "has mesoparasite"
    HAS_PARASITOID = "has parasitoid"
    KLEPTOPARASITIZED_BY = "kleptoparasitized by"
    RESERVOIR_HOST_OF = "reservoir host of"
    PARASITE_HOST_INTERACTION = "interacts with via parasite-host interaction"
    MUTUALISTICALLY_INTERACTS_WITH = "mutualisitcally interacts with"
    POLLINATED_BY = "pollinated by"
    POLLINATES = "pollinates"
    TROPHICALLY_INTERACTS_WITH = "trophically interacts with"
    PREYED_UPON_BY = "preyed upon by"
    PREYS_ON = "preys on"
    SYMBIOTROPHICALLY_INTERACTS_WITH = "symbiotrophically interacts with"
    TROPHIC_PARASITE_OF = "trophic parasite of"
    VISITED_BY = "visited by"
    HAS_EGGS_LAID_ON_BY = "has eggs laid on by"
    HAS_FLOWERS_VISITED_BY = "has flowers visited by"
    VISITS = "visits"
    LAYS_EGGS_ON = "lays eggs on"
    VISITS_FLOWERS_OF = "visits flowers of"
    PROVIDES_NUTRIENTS_FOR = "provides nutrients for"
    CREATES_HABITAT_FOR = "creates habitat for"
    TRANSMITTED_BY = "transmitted by"
    HAS_HABITAT = "has habitat"
    HAS_ROOST = "has roost"
    ECOLOGICALLY_CO_OCCURS_WITH = "ecologically co-occurs with"
    CO_ROOSTS_WITH = "co-roosts with"
    DISPERSES = "disperses"
    IS_DISPERSED_BY = "is dispersed by"
    IN_COMPETITION_WITH = "in competition with"


class EvidenceType(StrEnum):
    """How the paper supports its reported interactions."""

    DIRECT_OBSERVATION = "direct observation"
    CORRELATIONAL = "correlational"


class StrictExtractionModel(BaseModel):
    """Shared configuration for LLM-produced structured data."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SpeciesInteraction(StrictExtractionModel):
    """One directional interaction supported by the paper."""

    source_taxon_name: str = Field(
        min_length=1,
        description=(
            "Scientific name of the source taxon as stated in the paper. Do not "
            "externally normalize the name or invent a more specific taxon."
        ),
    )
    interaction_type_name: InteractionType = Field(
        description=(
            "Controlled directional relationship. The direction must agree with "
            "source_taxon_name and target_taxon_name."
        )
    )
    target_taxon_name: str = Field(
        min_length=1,
        description=(
            "Scientific name of the target taxon as stated in the paper. Do not "
            "record vague non-taxonomic groups such as 'small birds'."
        ),
    )
    part_of_target_taxon: str | None = Field(
        description=(
            "Part of the target involved in the interaction, such as seed, fruit, "
            "flower, egg, chick, larva, or carrion. Null when not stated."
        ),
    )
    time_of_occurrence: str | None = Field(
        description=(
            "Period when this interaction occurs, such as a season or month. Only "
            "extract it when the paper ties the period to the interaction itself; "
            "do not copy the study sampling period automatically."
        ),
    )
    locality_name: str | None = Field(
        description=(
            "Study locality stated in the paper, including the country and any "
            "more precise named area available. Null when not reported."
        ),
    )
    decimal_latitude: float | None = Field(
        ge=-90,
        le=90,
        description=(
            "Latitude reported by the paper, converted to decimal degrees. Do not "
            "geocode a place name to create a coordinate."
        ),
    )
    decimal_longitude: float | None = Field(
        ge=-180,
        le=180,
        description=(
            "Longitude reported by the paper, converted to decimal degrees. Do not "
            "geocode a place name to create a coordinate."
        ),
    )
    observation_date_time: str | None = Field(
        description=(
            "Year or range of years in which the underlying observations were "
            "collected, preserving the precision stated in the paper."
        ),
    )
    remarks: str | None = Field(
        description=(
            "Paper-supported qualification needed to interpret this interaction, "
            "such as uncertainty, assumptions, or methodological limitations."
        ),
    )


class PaperInteractionExtraction(StrictExtractionModel):
    """All Jantzen-standard interactions extractable from one paper."""

    evidence_type: EvidenceType | None = Field(
        description=(
            "Whether the paper supports the extracted interactions directly "
            "(for example observations, camera traps, DNA, or gut contents) or "
            "through a reported correlation. Null when this cannot be determined."
        ),
    )
    interactions: list[SpeciesInteraction] = Field(
        description=(
            "Distinct interactions supported by the paper. Return an empty list "
            "when the paper contains no extractable interaction at sufficient "
            "taxonomic resolution."
        ),
    )
