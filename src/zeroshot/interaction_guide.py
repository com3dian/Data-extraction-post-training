"""Directional meanings for all Jantzen interaction labels.

Names and available definitions come from data/source/Jantzen_species_interaction/
interaction_list.csv. Missing definitions and the short clarifications below
were written for the zero-shot prompt; the CSV remains the vocabulary source.
"""

INTERACTION_EXPLANATIONS: dict[str, str] = {
    "eats": "A consumes B or a stated part of B.",
    "acquires nutrients from": (
        "used when the target of the relation is not itself consumed, and does "
        "not have integral parts consumed, but provided nutrients in some other "
        "fashion"
    ),
    "is eaten by": "A or a stated part of A is consumed by B; inverse of eats.",
    "participates in a abiotic-biotic interaction with": (
        "biotic interaction relationship in which one partner is an organism "
        "and the other partner is inorganic. For example, the relationship "
        "between a sponge and the substrate to which is it anchored."
    ),
    "participates in a biotic-biotic interaction with": (
        "A and B are organisms that interact; use only when the paper does not "
        "support a more specific relation."
    ),
    "allelopath of": (
        "relationship between organisms where one organism is influenced by the "
        "biochemicals produced by another (one organism releases chemicals to "
        "positively or negatively influence the growth, survival or "
        "reproduction of other organisms in its vicinity)"
    ),
    "has allelopath": "inverse of allelopath",
    "has vector": "A is an agent transmitted by vector organism B.",
    "is killed by": "A is killed by B.",
    "is vector for": "A is a vector that transmits agent B.",
    "kills": "A kills B.",
    "symbiotically interacts with": (
        "biotic interaction in which the two organisms live together in more or "
        "less intimate association"
    ),
    "commensually interacts with": (
        "interaction relationship between two organisms living together in more "
        "or less intimate association in a relationship in which one benefits "
        "and the other is unaffected"
    ),
    "epiphyte of": (
        "interaction relationship wherein a plant or algae is living on the "
        "outside surface of another plant"
    ),
    "has epiphyte": "inverse of epiphyte of",
    "has host": (
        "X 'has host' y if and only if: x is an organism, y is an organism, and "
        "x can live on the surface of or within the body of y"
    ),
    "has reservoir host": "inverse of reservoir host of",
    "hyperparasite of": (
        "x is a hyperparasite of y iff x is a parasite of a parasite of the target organism y"
    ),
    "parasite of": (
        "parasite-host relationship where an organism benefits at the expense of another"
    ),
    "ectoparasite of": "A is a parasite living on the outside of host B.",
    "endoparasite of": "A is a parasite living inside host B.",
    "intercellular endoparasite of": (
        "sub-relation of endoparasite-of in which the parasite inhabits the "
        "spaces between host cells"
    ),
    "intracellular endoparasite of": (
        "sub-relation of endoparasite-of in which the parasite inhabits host cells"
    ),
    "facultative parasite of": (
        "sub-relations of parasite-of in which the parasite that can complete "
        "its life cycle independent of a host"
    ),
    "hemiparasite of": (
        "A is a photosynthetic plant that also takes water or nutrients from host B."
    ),
    "kleptoparasite of": (
        "Sub-relation of parasite of in which a parasite steals resources from "
        "another organism, usually food or nest material"
    ),
    "lays eggs in": "A deposits eggs inside B.",
    "mesoparasite of": (
        "sub-relation of parasite-of in which the parasite is partially an "
        "endoparasite and partially an ectoparasite"
    ),
    "obligate parasite of": (
        "sub-relation of parasite-of in which the parasite that cannot complete "
        "its life cycle without a host"
    ),
    "parasitoid of": (
        "A develops on or in host B and ultimately kills or sterilizes B; this "
        "is not a label for a disease agent."
    ),
    "root parasite of": (
        "parasite-of relationship in which the host is a plant and the parasite "
        "that attaches to the host root"
    ),
    "stem parasite of": (
        "parasite-of relationship in which the host is a plant and the parasite "
        "that attaches to the host stem"
    ),
    "pathogen of": "A is a disease-causing agent of host B.",
    "host of": "usually used for the larger (macro) of the two members of a symbiosis",
    "has pathogen": "A is a host with disease-causing agent B.",
    "hyperparasitized by": "A is a parasite that is itself parasitized by B.",
    "parasitized by": "A is a host parasitized by B.",
    "has ectoparasite": "A is a host with an external parasite B.",
    "has eggs laid in by": "A has eggs deposited inside it by B.",
    "has endoparasite": "A is a host with an internal parasite B.",
    "has intercellular endoparasite": "inverse of intercellular endoparasite of",
    "has intracellular endoparasite": "A is a host with parasite B living inside its cells.",
    "has mesoparasite": ("A is a host with parasite B living partly inside and partly outside it."),
    "has parasitoid": "A is a host of parasitoid B, which kills or sterilizes A.",
    "kleptoparasitized by": "A has food or other resources stolen by B.",
    "reservoir host of": "Host A naturally maintains agent B as a reservoir.",
    "interacts with via parasite-host interaction": (
        "interaction relationship between two organisms living together in more "
        "or less intimate association in a relationship in which association is "
        "disadvantageous or destructive to one of the organisms"
    ),
    "mutualisitcally interacts with": (
        "interaction relationship between two organisms living together in more "
        "or less intimate association in a relationship in which both organisms "
        "benefit from each other"
    ),
    "pollinated by": "A is a plant pollinated by B.",
    "pollinates": "A transfers pollen to plant B.",
    "trophically interacts with": (
        "interaction relationship in which the partners are related via a feeding relationship"
    ),
    "preyed upon by": "A is prey killed by predator B for food.",
    "preys on": "Predator A kills B to eat it or feed it to others.",
    "symbiotrophically interacts with": (
        "trophic interaction in which one organism acquires nutrients through a "
        "symbiotic relationship with another organism"
    ),
    "trophic parasite of": (
        "symbiotrophic interaction in which one organism acquires nutrients "
        "through a parasitic relationship with another organism"
    ),
    "visited by": "A is visited by B, with no more specific action established.",
    "has eggs laid on by": "A has eggs deposited on its outer surface by B.",
    "has flowers visited by": "The flowers of plant A are visited by B.",
    "visits": "A visits B, with no more specific action established.",
    "lays eggs on": (
        "interaction relationship in which organism a lays eggs on the outside "
        "surface of organism b. Organism b is neither helped nor harmed in the "
        "process of egg laying or incubation."
    ),
    "visits flowers of": "A visits the flowers of plant B.",
    "provides nutrients for": (
        "biotic interaction where a material entity provides nutrition for an organism"
    ),
    "creates habitat for": (
        "interaction relationship wherein one organism creates a structure or "
        "environment that is lived in by another organism"
    ),
    "transmitted by": "Disease or agent A is transmitted by vector organism B.",
    "has habitat": "Organism A lives or grows in habitat B.",
    "has roost": (
        "x 'has roost' y if and only if: x is an organism, y is a habitat, and "
        "y can support rest behaviors x (population of xs will possess "
        "adaptations (either evolved naturally or via artifical selection) "
        "which permit it to rest in y)"
    ),
    "ecologically co-occurs with": (
        "interaction relationship describing organisms that often occur "
        "together at the same time and space or in the same environment"
    ),
    "co-roosts with": "Organisms A and B share a roost site.",
    "disperses": "A moves the seeds or other propagules of plant B.",
    "is dispersed by": "The seeds or other propagules of plant A are moved by B.",
    "in competition with": (
        "an indirect association that one interactor competes with another "
        "interactor in a specfiic process."
    ),
}


def interaction_type_guide() -> str:
    """Explain each permitted label using A as source and B as target."""
    return "\n".join(f"- {name}: {meaning}" for name, meaning in INTERACTION_EXPLANATIONS.items())
