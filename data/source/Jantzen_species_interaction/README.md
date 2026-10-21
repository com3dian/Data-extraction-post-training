## README ###

File: papers_searched.csv

Content: Includes all the papers I looked at for this specific species

Columns:
- Paper ID: unique ID for each paper
- Taxon: Taxon I searched for
- Reference DOI: DOI of publication, if not available = NA
- Link to paper: Link where the paper is accessible (not always the journal website, often also other platforms e.g., ResearchGate)
- Used: indicates whether or not I exracted any interactions from the paper (y = yes, n = no). Each paper marked with y should occur in the _interaction_data_ file
- Type of evidence: indicates whether there is direct evidence for an observation ("direct observation") or whether interactions are assumed based on correlations (e.g., of population numbers and food abundance); is only filled for papers markes with "y"" in column "Used"
- Remarks: remarks that are mainly relevant for myself, but sometimes explain why a paper is not included (e.g., experimental papers, artifical feeding, different language)
- Full Reference (APA): full (APA) reference of the paper


File: species_list.csv

Content: Contains all the species that are included in the interaction data (note: these are all species from the full dataset, while the subset I made for you contains only a fraction of these species). All these species can potentially occur in the Netherlands according to GBIF

Columns:
- Date(s) searched: Dat on which I retrieved the papers from Scopus and Web of Science
- sourceTaxonName: scientific name of a taxon
- taxonomyStatus: whether the sourceTaxonName is an accepted name or a synonym (only accepted names should be enteres into the interaction_data.csv)
- taxonomicLevel: Which taxonomic level the sourceTaxonName is, e.g., order, Genus, Species 
- Common name: common English name of sourceTaxonName; sometime contains NA as there are no common English names
- OntologyID: the GBIF ID of the entry of the sourceTaxon (allows clear identification of each taxon)
- Remarks: Remarks
- Search string: The search string I used for that taxon to get relevant papers in Web of Science and Scopus (only filled for target species that have been done already)


File: interaction_data.csv

Content: The exracted data collected from the papers that specify the interactions between two taxa

Columns:
- Paper ID: unique ID for each paper (equivalent to Paper ID in papers-searched.csv)
- Reference DOI: DOI of publication, if not available = NA
- sourceTaxonName: scientific name of a taxon; Note: the direction of the interaction does not matter, as lons as the interactionTypeName specifies the direction correctly (means sourceTaxon and targetTaxon could be swapped, if the interactionTypeName is changed (e.g., A eats B is equivalent to B is eaten by A))
-interactionTypeName: specifies the interaction between sourceTaxon and targetTaxon and has to be one of the interactions specified in the interaction_list.csv
- targetTaxonName: scientific name of a taxon; see note of sourceTaxonName
- PartOfTargetTaxon: specifies which part of the target taxon is interacted with (if specified); this can be anything, e.g. seeds, flowers, nests, chicks, larvae
- timeOfOccurence: specifies that this interaction occurs in a certain time period. This is not always stated in papers and is not eual to the time the data was collected (i.e., only because dietary information was collected in the breeding season, doesn't add "breeding season" to this column). It should only be filled if it is clear that this interaction (only) occurs in a certain period (e.g., bird eats seed in atumun but flowers in spring); note: if the same interaction  occurs during different times, they are all noted in an extra row)
- localityName: location where the study was conducted, should at least contain country (for multi-country studies all countries), and if a city, certain National Park or geographic area is mentioned also that (e.g., Veluwe, Netherlands)
- decimalLatitude: latitude in decimals
- decimalLongitude: longitude in decimals
-observationDateTime: (range) of years in which the study was conducted
- Remarks: remarks


File: interaction_list.csv

Content: Contains all possible interaction types we record with their ontological deifinitions (if available)

Columns:
- Ontology reference (IRI): IRI referring to the ontology term of the interaction type
- interactionTypeName: name of interaction type (identical to same column in interaction_data.csv)
- Parent term (IRI): IRI refereing to the parent term in ontology
- Parent term label: name of the parent term
- Alternative term: gives an alternative name
- Definition: defines the interaction type