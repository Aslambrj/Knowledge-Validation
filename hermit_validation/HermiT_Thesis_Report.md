# Ontology-Based Knowledge Graph Validation with HermiT

## Empirical report

This report is generated from the local source files and experiment artifacts
produced by `run_experiments.py`. It reports no metric or result that was not
measured in those runs. The “Wikidata” and “DBpedia” inputs present in this
workspace are the local film-focused RDF extracts named in the dataset inventory,
not claims about complete public knowledge graphs.

## Methodology

The OWL 2 ontology records sampled source assertions as named individuals,
object-property assertions, and lexical string-valued data-property assertions.
For the controlled benchmark only, training-partition relation signatures are
encoded as disjoint observed/unobserved domain and range classes, with explicit
candidate-entity membership assertions. These are experimental constraints,
not authoritative source schema. HermiT classifies named candidate classes defined
by the candidate assertion; unsatisfiability is the predicted corruption label.
The toy test checks the installed HermiT's consistency and inconsistency paths.

## Experimental setup

- Reasoner: HermiT, invoked through Owlready2 `sync_reasoner`.
- Software versions: HermiT `1.3.8.1099`, Owlready2
  `0.51`, Java `21`, Python
  `3.14.7`.
- Random seed: `42`.
- Controlled sample: up to `2000` triples per dataset (up to
  `1600` train, `200` validation, and
  `200` test triples), with seed `42`; official local splits
  are preserved where available. No download occurs.
- Data acquisition: none. Only the files already present under `datasets/`
  are read.
- Each notebook uses the shared `hermit_validation.py` pipeline. Notebook cell
  layout, functions, parameters, outputs, and evaluation logic are identical;
  the dataset key (and consequently its local file path) is the only difference.
- The benchmark uses held-out source assertions as valid candidates and
  relation-signature corruptions as injected-error candidates; calibration and
  evaluation pools are capped at `50` and `50` per
  applicable category, respectively. This smaller sample and case pool reduces
  runtime and statistical power; report results as a controlled sample benchmark,
  not as full-dataset performance or real-world error detection absent an
  external oracle.

## Dataset-wise results

| Dataset | Source files | Source rows | Unique source triples | Sample triples | HermiT consistency | HermiT runtime (s) |
|---|---|---:|---:|---:|---|---:|
| Wikidata | `datasets\wikidata film\wikidata_film_kg_10k_v4.tsv` | 64163 | 64163 | 2000 | CONSISTENT | 7.069903 |
| DBpedia | `datasets\dbpedia film\dbpedia_film_kg_10k_v9.tsv` | 89794 | 89794 | 2000 | CONSISTENT | 11.574929 |
| FB15K-237 | `datasets\FB15K-237\train.txt, datasets\FB15K-237\valid.txt, datasets\FB15K-237\test.txt` | 310116 | 310116 | 2000 | CONSISTENT | 10.680221 |
| WN18RR | `datasets\WN18RR\train.txt, datasets\WN18RR\valid.txt, datasets\WN18RR\test.txt` | 93003 | 93003 | 2000 | CONSISTENT | 5.514645 |
| YAGO3-10 | `datasets\YAGO3-10\train.csv, datasets\YAGO3-10\valid.csv, datasets\YAGO3-10\test.csv` | 1089040 | 1089040 | 2000 | CONSISTENT | 5.735044 |

The table reports clean sampled-ontology consistency and the measured HermiT
runtime; category classification results appear below. Runtime is elapsed wall
time on this machine and is not a general performance estimate.

## Ontology construction statistics

| Dataset | Individuals | Object properties | Data properties | Object assertions | Data assertions |
|---|---:|---:|---:|---:|---:|
| Wikidata | 1974 | 7 | 1 | 1292 | 308 |
| DBpedia | 1851 | 7 | 0 | 1600 | 0 |
| FB15K-237 | 2376 | 192 | 0 | 1600 | 0 |
| WN18RR | 2895 | 10 | 0 | 1600 | 0 |
| YAGO3-10 | 2824 | 33 | 0 | 1600 | 0 |

The ontology declares a generic `KGEntity` class and properties needed to encode
the sample. Both the clean ontology and a separate benchmark ontology are saved
alongside the reasoned ontology, case records, metrics, and logs in `results/`.

## Error injection and evaluation

Injected corruptions are positive class `1`; held-out source assertions are
valid class `0`. The confusion matrix compares this generated label with
HermiT's binary unsatisfiable/satisfiable classification. This is an empirical
benchmark and not independent real-world ground truth. `Duplicate Fact` uses a
near-duplicate tail corruption because OWL set semantics collapse identical
axioms. `Missing Relation` evaluates held-out candidate compatibility only;
unasserted facts are not considered false under the Open World Assumption.

### Measured category results

| Dataset | Error category | Cases | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | ROC-AUC | Runtime (s) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Wikidata | Domain | 30 | 15 | 2 | 13 | 0 | 0.5666666666666667 | 0.5357142857142857 | 1.0 | 0.6976744186046512 | 0.5666666666666667 | 7.069903 |
| Wikidata | Range | 30 | 15 | 2 | 13 | 0 | 0.5666666666666667 | 0.5357142857142857 | 1.0 | 0.6976744186046512 | 0.5666666666666667 | 7.069903 |
| Wikidata | Entity Type | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| Wikidata | Duplicate Fact | 74 | 37 | 37 | 0 | 0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 7.069903 |
| Wikidata | Missing Relation | 30 | 14 | 2 | 13 | 1 | 0.5333333333333333 | 0.5185185185185185 | 0.9333333333333333 | 0.6666666666666667 | 0.5333333333333333 | 7.069903 |
| Wikidata | Cross-KG Conflict | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| Wikidata | Temporal/Contextual | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| DBpedia | Domain | 50 | 25 | 17 | 8 | 0 | 0.84 | 0.7575757575757576 | 1.0 | 0.8620689655172413 | 0.8400000000000001 | 11.574929 |
| DBpedia | Range | 50 | 25 | 17 | 8 | 0 | 0.84 | 0.7575757575757576 | 1.0 | 0.8620689655172413 | 0.8400000000000001 | 11.574929 |
| DBpedia | Entity Type | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| DBpedia | Duplicate Fact | 100 | 50 | 50 | 0 | 0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 11.574929 |
| DBpedia | Missing Relation | 50 | 17 | 17 | 8 | 8 | 0.68 | 0.68 | 0.68 | 0.68 | 0.68 | 11.574929 |
| DBpedia | Cross-KG Conflict | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| DBpedia | Temporal/Contextual | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| FB15K-237 | Domain | 38 | 19 | 1 | 18 | 0 | 0.5263157894736842 | 0.5135135135135135 | 1.0 | 0.6785714285714285 | 0.5263157894736842 | 10.680221 |
| FB15K-237 | Range | 38 | 19 | 1 | 18 | 0 | 0.5263157894736842 | 0.5135135135135135 | 1.0 | 0.6785714285714285 | 0.5263157894736842 | 10.680221 |
| FB15K-237 | Entity Type | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| FB15K-237 | Duplicate Fact | 100 | 50 | 50 | 0 | 0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 10.680221 |
| FB15K-237 | Missing Relation | 38 | 19 | 1 | 18 | 0 | 0.5263157894736842 | 0.5135135135135135 | 1.0 | 0.6785714285714285 | 0.5263157894736842 | 10.680221 |
| FB15K-237 | Cross-KG Conflict | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| FB15K-237 | Temporal/Contextual | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| WN18RR | Domain | 8 | 4 | 0 | 4 | 0 | 0.5 | 0.5 | 1.0 | 0.6666666666666666 | 0.5 | 5.514645 |
| WN18RR | Range | 8 | 4 | 0 | 4 | 0 | 0.5 | 0.5 | 1.0 | 0.6666666666666666 | 0.5 | 5.514645 |
| WN18RR | Entity Type | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| WN18RR | Duplicate Fact | 100 | 50 | 50 | 0 | 0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 5.514645 |
| WN18RR | Missing Relation | 8 | 3 | 0 | 4 | 1 | 0.375 | 0.42857142857142855 | 0.75 | 0.5454545454545454 | 0.375 | 5.514645 |
| WN18RR | Cross-KG Conflict | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| WN18RR | Temporal/Contextual | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| YAGO3-10 | Domain | 2 | 1 | 0 | 1 | 0 | 0.5 | 0.5 | 1.0 | 0.6666666666666666 | 0.5 | 5.735044 |
| YAGO3-10 | Range | 2 | 1 | 0 | 1 | 0 | 0.5 | 0.5 | 1.0 | 0.6666666666666666 | 0.5 | 5.735044 |
| YAGO3-10 | Entity Type | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| YAGO3-10 | Duplicate Fact | 100 | 50 | 50 | 0 | 0 | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 5.735044 |
| YAGO3-10 | Missing Relation | 2 | 1 | 0 | 1 | 0 | 0.5 | 0.5 | 1.0 | 0.6666666666666666 | 0.5 | 5.735044 |
| YAGO3-10 | Cross-KG Conflict | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| YAGO3-10 | Temporal/Contextual | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A | N/A |

`ROC-AUC` is the binary-score AUC (equivalent here to balanced accuracy).
`MRR`/`Hits@K` are N/A because HermiT does not rank candidates. Cross-KG
conflict and temporal/contextual metrics are N/A because the local inputs lack
validated entity alignment and temporal/context labels/rules. The workbook's
`Overall_Metrics` sheet contains the dataset/category aggregates; individual
candidate assertions and predictions are in `Case_Level_Results`.

## Applicability and limitations

| Dataset | Error category | Applicability | Methodological reason |
|---|---|---|---|
| Wikidata | Domain | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. |
| Wikidata | Range | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. |
| Wikidata | Entity Type | N/A | N/A: this dataset does not provide independently validated entity classes and disjointness/type constraints needed to adjudicate type-conflict cases. |
| Wikidata | Duplicate Fact | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. This mirrors the reference pipeline's near-duplicate-tail protocol; OWL itself cannot distinguish repeated copies of an identical axiom. |
| Wikidata | Missing Relation | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. The task is held-out link-candidate compatibility, not proof that an absent triple is false under OWL's Open World Assumption. |
| Wikidata | Cross-KG Conflict | N/A | N/A: a single dataset is evaluated per notebook, and no independently validated cross-KG entity alignment is supplied. |
| Wikidata | Temporal/Contextual | N/A | N/A: local triples do not provide validated temporal qualifiers, context labels, or temporal truth rules. |
| DBpedia | Domain | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. |
| DBpedia | Range | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. |
| DBpedia | Entity Type | N/A | N/A: this dataset does not provide independently validated entity classes and disjointness/type constraints needed to adjudicate type-conflict cases. |
| DBpedia | Duplicate Fact | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. This mirrors the reference pipeline's near-duplicate-tail protocol; OWL itself cannot distinguish repeated copies of an identical axiom. |
| DBpedia | Missing Relation | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. The task is held-out link-candidate compatibility, not proof that an absent triple is false under OWL's Open World Assumption. |
| DBpedia | Cross-KG Conflict | N/A | N/A: a single dataset is evaluated per notebook, and no independently validated cross-KG entity alignment is supplied. |
| DBpedia | Temporal/Contextual | N/A | N/A: local triples do not provide validated temporal qualifiers, context labels, or temporal truth rules. |
| FB15K-237 | Domain | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. |
| FB15K-237 | Range | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. |
| FB15K-237 | Entity Type | N/A | N/A: this dataset does not provide independently validated entity classes and disjointness/type constraints needed to adjudicate type-conflict cases. |
| FB15K-237 | Duplicate Fact | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. This mirrors the reference pipeline's near-duplicate-tail protocol; OWL itself cannot distinguish repeated copies of an identical axiom. |
| FB15K-237 | Missing Relation | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. The task is held-out link-candidate compatibility, not proof that an absent triple is false under OWL's Open World Assumption. |
| FB15K-237 | Cross-KG Conflict | N/A | N/A: a single dataset is evaluated per notebook, and no independently validated cross-KG entity alignment is supplied. |
| FB15K-237 | Temporal/Contextual | N/A | N/A: local triples do not provide validated temporal qualifiers, context labels, or temporal truth rules. |
| WN18RR | Domain | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. |
| WN18RR | Range | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. |
| WN18RR | Entity Type | N/A | N/A: this dataset does not provide independently validated entity classes and disjointness/type constraints needed to adjudicate type-conflict cases. |
| WN18RR | Duplicate Fact | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. This mirrors the reference pipeline's near-duplicate-tail protocol; OWL itself cannot distinguish repeated copies of an identical axiom. |
| WN18RR | Missing Relation | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. The task is held-out link-candidate compatibility, not proof that an absent triple is false under OWL's Open World Assumption. |
| WN18RR | Cross-KG Conflict | N/A | N/A: a single dataset is evaluated per notebook, and no independently validated cross-KG entity alignment is supplied. |
| WN18RR | Temporal/Contextual | N/A | N/A: local triples do not provide validated temporal qualifiers, context labels, or temporal truth rules. |
| YAGO3-10 | Domain | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. |
| YAGO3-10 | Range | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. |
| YAGO3-10 | Entity Type | N/A | N/A: this dataset does not provide independently validated entity classes and disjointness/type constraints needed to adjudicate type-conflict cases. |
| YAGO3-10 | Duplicate Fact | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. This mirrors the reference pipeline's near-duplicate-tail protocol; OWL itself cannot distinguish repeated copies of an identical axiom. |
| YAGO3-10 | Missing Relation | Applicable (synthetic benchmark) | Controlled benchmark: source-positive facts are held-out training-partition examples (or known training facts for near-duplicate tests); negative labels are assigned to generated corruption by construction. HermiT evaluates consistency against training-derived empirical relation signatures, which are experimental closed-world constraints, not authoritative ontology semantics. The task is held-out link-candidate compatibility, not proof that an absent triple is false under OWL's Open World Assumption. |
| YAGO3-10 | Cross-KG Conflict | N/A | N/A: a single dataset is evaluated per notebook, and no independently validated cross-KG entity alignment is supplied. |
| YAGO3-10 | Temporal/Contextual | N/A | N/A: local triples do not provide validated temporal qualifiers, context labels, or temporal truth rules. |

### Why Entity Type is N/A

Entity Type is reported as `N/A` because the local datasets do not provide
independently validated entity-type assertions together with authoritative
class-disjointness axioms. This is a limitation of the available evidence and
benchmark setup, **not a limitation of HermiT**: HermiT can detect an
inconsistent type assignment when incompatible class memberships and the
relevant disjointness axioms are explicitly present in the ontology. Creating
those type labels or disjointness rules from the same triples under evaluation
would make the test circular and would not establish an independently grounded
error label. Therefore, no Entity Type cases are generated and no score is
claimed for that category. If an external, validated type ontology and
disjointness constraints become available, this category can be evaluated
separately.

Empirical domain/range signatures and generated labels make a controlled
classification benchmark possible, but they do not establish authoritative
domain/range truth. Cross-KG conflict and temporal/contextual validity, ranking
metrics, and per-case runtime distribution are also unsupported. Results should
not be generalized to real-world validation without independently sourced
schema and labels.

## Discussion

Results quantify HermiT's behavior on the explicitly stated, train-derived
controlled benchmark. Under OWL 2 Direct Semantics, the explicit finite
signatures and disjoint observed/unobserved classes are experimental
assumptions, not discovered source semantics.
The Open World Assumption still means an unasserted fact is not refuted.

## References

1. Motik, B., Shearer, R., & Horrocks, I. (2009). Hypertableau Reasoning for
   Description Logics. *Journal of Artificial Intelligence Research*, 36,
   165–228. https://doi.org/10.1613/jair.2811
2. Shearer, R., Motik, B., & Horrocks, I. (2008). HermiT: A Highly-Efficient
   OWL Reasoner. *Proceedings of the OWLED 2008 DC Workshop on OWL:
   Experiences and Directions*. https://ceur-ws.org/Vol-432/owled2008eu_submission_21.pdf
3. W3C. (2012). *OWL 2 Web Ontology Language: Structural Specification and
   Functional-Style Syntax (Second Edition)*. W3C Recommendation.
   https://www.w3.org/TR/owl2-syntax/
4. W3C. (2012). *OWL 2 Web Ontology Language: Direct Semantics (Second
   Edition)*. W3C Recommendation. https://www.w3.org/TR/owl2-direct-semantics/
5. Tao, J., Sirin, E., Bao, J., & McGuinness, D. (2010). Integrity Constraints
   in OWL. *Proceedings of the AAAI Conference on Artificial Intelligence*,
   24(1), 1443–1448. https://doi.org/10.1609/aaai.v24i1.7525
6. Labra Gayo, J. E., Prud'hommeaux, E., Boneva, I., & Kontokostas, D. (2018).
   *Validating RDF Data*. Synthesis Lectures on Data, Semantics, and Knowledge.
   https://doi.org/10.1007/978-3-031-79478-0
7. W3C. (2017). *Shapes Constraint Language (SHACL)*. W3C Recommendation.
   https://www.w3.org/TR/shacl/
8. Hogan, A., Blomqvist, E., Cochez, M., d’Amato, C., de Melo, G., Gutierrez,
   C., Kirrane, S., Labra Gayo, J. E., Navigli, R., Neumaier, S., Ngomo,
   A.-C. N., Polleres, A., Rashid, S. M., Rula, A., Schmelzeisen, L.,
   Sequeda, J., Staab, S., & Zimmermann, A. (2021). Knowledge Graphs.
   *ACM Computing Surveys*, 54(4), Article 71.
   https://doi.org/10.1145/3447772

## Reproducibility outputs

- Master workbook: `HermiT_Master_Results.xlsx` (category candidate details are included
  in `Overall_Metrics`; no separate category tabs are generated)
- Executed dataset notebooks: `01_Wikidata_HermiT.ipynb` through
  `05_YAGO3-10_HermiT.ipynb`
- Results directory: `results/`
- Dependency manifest: `requirements.txt`
- Shared implementation: `hermit_validation.py`
- Notebook factory/runner: `create_notebooks.py`, `run_experiments.py`
