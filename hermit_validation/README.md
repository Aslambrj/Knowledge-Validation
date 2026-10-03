# HermiT knowledge-graph validation experiment

This workspace contains a repeatable OWL 2 / HermiT experiment over the dataset
files already present in `datasets/`. It does not download dataset content.

## Run all five datasets

```powershell
.\.venv\Scripts\python.exe hermit_validation.py
```

The single script runs the HermiT sanity check and then loads and evaluates
Wikidata, DBpedia, FB15K-237, WN18RR, and YAGO3-10 in sequence. Each dataset
uses its own local source files and training split. To run a subset, pass one
or more configured dataset names:

```powershell
.\.venv\Scripts\python.exe hermit_validation.py --datasets Wikidata WN18RR
```

## Fixed experimental parameters

- Runtime versions for HermiT, Owlready2, Java, and Python are recorded in the
  dataset summaries and thesis report.
- Seed: `42`.
- Sample: up to `2,000` triples per dataset (`1,600` train, `200` validation,
  and `200` test), with official train/valid/test splits preserved where
  available. Single-file extracts are deterministically partitioned into
  train/validation/test samples. Full local files are streamed for dataset-wide
  counts.
- Duplicate sample rows are removed before building the clean ontology.
- All notebooks use the same ordered cells and shared implementation. The
  dataset key selects only the local file path.
- Each applicable category has a held-out valid candidate pool and a generated
  corruption pool, capped at `50` calibration and `50` evaluation queries per
  category. HermiT classifies candidate classes against training-derived finite
  relation signatures in one batch. Corruption is the positive label; an
  unsatisfiable candidate is predicted as an error. These reduced sample and
  case counts run faster but have lower statistical power; report the metrics
  as a controlled sample benchmark, not full-dataset performance or independently
  verified real-world errors.
- Cross-KG Conflict and Temporal/Contextual are `N/A` without aligned KGs or
  validated temporal/context facts. Entity Type is `N/A` without independently
  validated entity classes and type-disjointness constraints.
- `Duplicate Fact` uses a disclosed near-duplicate tail corruption protocol:
  OWL set semantics cannot distinguish repeated copies of an identical axiom.
  `Missing Relation` measures held-out candidate compatibility and does not
  claim an absent fact is false under OWL's Open World Assumption.

The local Wikidata and DBpedia inputs are specifically the film-focused files
`wikidata_film_kg_10k_v4.tsv` and `dbpedia_film_kg_10k_v9.tsv`. They should not
be described as complete Wikidata or DBpedia dumps.

## Output files

- `01_Wikidata_HermiT.ipynb` through `05_YAGO3-10_HermiT.ipynb` — same pipeline
  and saved execution outputs.
- `results/` — per-dataset sampled clean facts, OWL ontologies, candidate case
  records, applicability, metrics, runtime and warnings/failures; also toy KG
  sanity outputs and the run manifest.
- `HermiT_Master_Results.xlsx` — summary, applicability, case-level,
  `Overall_Metrics`, runtime, and failure sheets. `Overall_Metrics` contains
  one dataset/category aggregate row, including confusion counts, classification
  metrics, coverage, measured runtime, applicability, and source/ontology
  statistics. Candidate assertions, labels, and predictions are in
  `Case_Level_Results`; separate per-category sheets are omitted.

Each notebook's final **Export Results** cell refreshes
`HermiT_Master_Results.xlsx` automatically as soon as that dataset finishes.
When running notebooks one at a time, the workbook includes completed datasets
so far; rerunning another notebook adds/refreshes its rows.
- `HermiT_Thesis_Report.md` — generated report with measured outcomes and
  explicit limitations.

## Interpretation and limits

The training-derived relation signatures and observed/unobserved class
disjointness assumptions are experimental finite-schema constraints, not authoritative
semantics supplied by the datasets. Accordingly, the populated scores evaluate
HermiT on the generated benchmark protocol only. They are not evidence of
real-world error-detection performance. Unsupported entity-type,
cross-KG-conflict, and temporal/contextual cases are `N/A` with reasons recorded.
OWL follows the Open World Assumption: in particular, absence is not negation,
so Missing Relation is reported only as held-out candidate compatibility.
`MRR` and `Hits@K` are also `N/A` because HermiT is a classifier, not a ranking
model. Aggregate HermiT batch runtime is measured; per-case median runtime is
not measurable from one shared classification run.

## Verified references

- Motik, Shearer, and Horrocks, “Hypertableau Reasoning for Description
  Logics,” *JAIR* 36 (2009), DOI: <https://doi.org/10.1613/jair.2811>.
- Tao, Sirin, Bao, and McGuinness, “Integrity Constraints in OWL,” *AAAI*
  24(1) (2010), DOI: <https://doi.org/10.1609/aaai.v24i1.7525>.
- Labra Gayo et al., *Validating RDF Data*, Synthesis Lectures on Data,
  Semantics, and Knowledge, DOI:
  <https://doi.org/10.1007/978-3-031-79478-0>.
- Shearer, Motik, and Horrocks, “HermiT: A Highly-Efficient OWL Reasoner,”
  OWLED 2008, <https://ceur-ws.org/Vol-432/owled2008eu_submission_21.pdf>.
- W3C, *OWL 2 Structural Specification and Functional-Style Syntax*:
  <https://www.w3.org/TR/owl2-syntax/>.
- W3C, *OWL 2 Direct Semantics*:
  <https://www.w3.org/TR/owl2-direct-semantics/>.
- W3C, *Shapes Constraint Language (SHACL)*:
  <https://www.w3.org/TR/shacl/>.
- Hogan et al., “Knowledge Graphs,” *ACM Computing Surveys* 54(4) (2021),
  DOI: <https://doi.org/10.1145/3447772>.
