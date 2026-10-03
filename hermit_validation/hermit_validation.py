"""Reproducible, OWL-semantics-aware HermiT validation experiments."""

from __future__ import annotations

import csv
import ctypes
import argparse
import hashlib
import json
import os
import platform
import random
import re
import subprocess
import sys
import threading
import tempfile
import time
import types
from contextlib import contextmanager
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
import zipfile

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from owlready2 import (
    AllDisjoint,
    DataProperty,
    ObjectProperty,
    OneOf,
    OwlReadyInconsistentOntologyError,
    Thing,
    get_ontology,
    sync_reasoner,
)


SEED = 42
SAMPLE_SIZE = 2_000
TRAIN_SAMPLE_SIZE = 1_600
VALIDATION_SAMPLE_SIZE = 200
TEST_SAMPLE_SIZE = 200
CALIB_QUERIES = 50
EVAL_QUERIES = 50
ERROR_CATEGORIES = (
    "Domain",
    "Range",
    "Entity Type",
    "Duplicate Fact",
    "Missing Relation",
    "Cross-KG Conflict",
    "Temporal/Contextual",
)
METRIC_COLUMNS = (
    "Dataset",
    "Error Category",
    "Cases",
    "TP",
    "TN",
    "FP",
    "FN",
    "Accuracy",
    "Precision",
    "Recall",
    "F1",
    "Detection Rate",
    "Avg Runtime",
    "Median Runtime",
)
METRIC_EXTRA_COLUMNS = (
    "Best Error",
    "Coverage",
    "ROC-AUC",
    "Threshold",
    "N_queries",
    "N_found",
    "MRR",
    "Hits@1",
    "Hits@3",
    "Hits@10",
    "Runtime_seconds",
    "Positive Class",
    "Applicability",
    "Protocol",
    "Notes",
)
OVERALL_COLUMNS = METRIC_COLUMNS + METRIC_EXTRA_COLUMNS + (
    "Source Triples",
    "Sampled Triples",
    "Ontology Individuals",
    "Clean KG HermiT Result",
    "Clean KG HermiT Runtime (seconds)",
)
CASE_COLUMNS = (
    "dataset",
    "case_id",
    "error_category",
    "split",
    "original_assertion",
    "modified_assertion",
    "ground_truth",
    "class_label",
    "prediction_score",
    "applicability",
    "methodological_reason",
    "validation_prediction",
    "reasoner_scope",
)
APPLICABILITY_COLUMNS = (
    "dataset",
    "error_category",
    "applicability",
    "methodological_reason",
)
FAILURE_COLUMNS = ("dataset", "stage", "severity", "message")

DATASET_CONFIGS: dict[str, dict[str, Any]] = {
    "Wikidata": {
        "directory": "wikidata film",
        "sources": (
            ("kg", "wikidata_film_kg_10k_v4.tsv", "\t"),
        ),
    },
    "DBpedia": {
        "directory": "dbpedia film",
        "sources": (
            ("kg", "dbpedia_film_kg_10k_v9.tsv", "\t"),
        ),
    },
    "FB15K-237": {
        "directory": "FB15K-237",
        "sources": (
            ("train", "train.txt", "\t"),
            ("valid", "valid.txt", "\t"),
            ("test", "test.txt", "\t"),
        ),
    },
    "WN18RR": {
        "directory": "WN18RR",
        "sources": (
            ("train", "train.txt", "\t"),
            ("valid", "valid.txt", "\t"),
            ("test", "test.txt", "\t"),
        ),
    },
    "YAGO3-10": {
        "directory": "YAGO3-10",
        "sources": (
            ("train", "train.csv", ","),
            ("valid", "valid.csv", ","),
            ("test", "test.csv", ","),
        ),
    },
}

SHEET_NAMES = (
    "Dataset_Summary",
    "Ontology_Statistics",
    "Applicability_Matrix",
    "Case_Level_Results",
    "Overall_Metrics",
    "Runtime_Analysis",
    "Failures_Logs",
)

TYPE_PREDICATE_MARKERS = (
    "rdf-syntax-ns#type",
    "/p31",
    "/instance_of",
    "/type",
)
DATE_PATTERN = re.compile(r"(?<!\d)(\d{4})(?:-\d{2}(?:-\d{2})?)?(?:[Tt ].*)?$")


@dataclass
class ExperimentRun:
    dataset: str
    project_root: Path
    started_at: float = field(default_factory=time.perf_counter)
    source_statistics: dict[str, Any] = field(default_factory=dict)
    sampled_triples: list[tuple[str, str, str]] = field(default_factory=list)
    clean_triples: list[tuple[str, str, str]] = field(default_factory=list)
    ontology: Any = None
    ontology_path: Path | None = None
    splits: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    entity_individuals: dict[str, Any] = field(default_factory=dict)
    relation_properties: dict[str, Any] = field(default_factory=dict)
    case_classes: dict[str, Any] = field(default_factory=dict)
    ontology_statistics: dict[str, Any] = field(default_factory=dict)
    cases: list[dict[str, Any]] = field(default_factory=list)
    calibration_cases: list[dict[str, Any]] = field(default_factory=list)
    applicability: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    reasoner_result: str = "NOT_RUN"
    reasoner_runtime: float | None = None
    validation_runtime: float | None = None
    metrics: list[dict[str, Any]] = field(default_factory=list)
    results_dir: Path | None = None


@contextmanager
def _timed(run: ExperimentRun, stage: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        run.timings[stage] = round(time.perf_counter() - started, 6)


def _record_failure(
    run: ExperimentRun, stage: str, severity: str, message: str
) -> None:
    run.failures.append(
        {
            "dataset": run.dataset,
            "stage": stage,
            "severity": severity,
            "message": message,
        }
    )


def _software_environment() -> dict[str, str]:
    import owlready2

    jar_path = Path(owlready2.__file__).parent / "hermit" / "HermiT.jar"
    with zipfile.ZipFile(jar_path) as archive:
        manifest_name = next(
            name for name in archive.namelist()
            if name.upper() == "META-INF/MANIFEST.MF"
        )
        manifest_lines = archive.read(manifest_name).decode(
            "utf-8", errors="replace"
        ).replace("\r\n ", "")
    hermit_match = re.search(
        r"^Implementation-Version:\s*(\S+)",
        manifest_lines,
        flags=re.MULTILINE,
    )
    if hermit_match is None:
        raise RuntimeError(f"HermiT version is absent from {jar_path}")

    java_path = os.environ.get("JAVA_HOME")
    java_executable = (
        str(Path(java_path) / "bin" / "java.exe")
        if java_path and os.name == "nt"
        else str(Path(java_path) / "bin" / "java")
        if java_path
        else "java"
    )
    java_version = subprocess.run(
        [java_executable, "-version"],
        check=True,
        capture_output=True,
        text=True,
    )
    java_output = java_version.stderr or java_version.stdout
    java_match = re.search(r'version "([^"]+)"', java_output)
    if java_match is None:
        raise RuntimeError(
            "Could not identify the Java version from `java -version` output."
        )
    return {
        "hermit": hermit_match.group(1),
        "owlready2": str(owlready2.VERSION),
        "java": java_match.group(1),
        "python": platform.python_version(),
    }


def _configure_hermit_tempdir(project_root: Path) -> Path:
    """Use a writable short Windows path because HermiT parses its input as an IRI."""
    actual_tempdir = project_root / ".hermit_tmp"
    actual_tempdir.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(
            str(actual_tempdir), buffer, len(buffer)
        )
        if not length or length >= len(buffer):
            raise RuntimeError(
                "Could not resolve an ASCII Windows short path for HermiT's "
                f"temporary directory: {actual_tempdir}"
            )
        reasoner_tempdir = Path(buffer.value)
        if " " in str(reasoner_tempdir) or not str(reasoner_tempdir).isascii():
            raise RuntimeError(
                "HermiT requires a temporary directory path without spaces or "
                f"non-ASCII characters; resolved path was {reasoner_tempdir}"
            )
    else:
        reasoner_tempdir = actual_tempdir

    try:
        with tempfile.NamedTemporaryFile(dir=reasoner_tempdir):
            pass
    except OSError as exc:
        raise RuntimeError(
            f"HermiT temporary directory is not writable: {reasoner_tempdir}"
        ) from exc

    return reasoner_tempdir


@contextmanager
def _hermit_temp_workspace(project_root: Path) -> Iterator[None]:
    temp_root = _configure_hermit_tempdir(project_root)
    call_tempdir = Path(tempfile.mkdtemp(prefix="reasoner_", dir=temp_root))
    previous_tempdir = tempfile.tempdir
    tempfile.tempdir = str(call_tempdir)
    try:
        yield
    finally:
        tempfile.tempdir = previous_tempdir
        for temporary_file in call_tempdir.iterdir():
            if not temporary_file.is_file():
                raise RuntimeError(
                    f"Unexpected non-file in HermiT temporary directory: "
                    f"{temporary_file}"
                )
            temporary_file.unlink()
        call_tempdir.rmdir()


def run_toy_sanity(project_root: Path) -> dict[str, Any]:
    """Verify HermiT accepts a consistent toy KG and rejects a known contradiction."""
    project_root = Path(project_root).resolve()
    output_dir = project_root / "results" / "Toy_KG_Sanity"
    output_dir.mkdir(parents=True, exist_ok=True)

    good = get_ontology("http://example.org/hermit-validation/toy-consistent.owl")
    with good:
        class Person(Thing):
            pass

        class Place(Thing):
            pass

        class locatedIn(ObjectProperty):
            domain = [Person]
            range = [Place]

        AllDisjoint([Person, Place])
        alice = Person("alice")
        city = Place("city")
        alice.locatedIn.append(city)
    good.save(file=str(output_dir / "toy_consistent.owl"), format="rdfxml")
    with _hermit_temp_workspace(project_root):
        sync_reasoner([good], debug=0)

    bad = get_ontology("http://example.org/hermit-validation/toy-inconsistent.owl")
    with bad:
        class Person(Thing):
            pass

        class Place(Thing):
            pass

        class locatedIn(ObjectProperty):
            domain = [Person]
            range = [Place]

        AllDisjoint([Person, Place])
        alice = Person("alice")
        person_as_location = Person("person_as_location")
        alice.locatedIn.append(person_as_location)
    bad_path = output_dir / "toy_inconsistent.owl"
    bad.save(file=str(bad_path), format="rdfxml")

    try:
        with _hermit_temp_workspace(project_root):
            sync_reasoner([bad], debug=0)
    except OwlReadyInconsistentOntologyError:
        result = {
            "toy_consistent_ontology": "CONSISTENT",
            "toy_inconsistent_ontology": "INCONSISTENT_AS_EXPECTED",
            "hermit_toy_sanity": "PASS",
            "software_environment": _software_environment(),
            "toy_ontology_files": [
                str(output_dir / "toy_consistent.owl"),
                str(bad_path),
            ],
        }
    else:
        raise AssertionError(
            "HermiT did not detect the known toy contradiction generated by "
            "the declared disjoint classes and range axiom."
        )

    (output_dir / "sanity_result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def _source_path(project_root: Path, dataset: str, filename: str) -> Path:
    config = DATASET_CONFIGS[dataset]
    return project_root / "datasets" / config["directory"] / filename


def _is_header(row: list[str]) -> bool:
    normalized = [column.strip().lower() for column in row]
    return normalized in (
        ["s", "p", "o"],
        ["subject", "predicate", "object"],
        ["head", "relation", "tail"],
    )


def _iter_source_rows(
    path: Path, delimiter: str
) -> Iterator[tuple[int, tuple[str, str, str], bool]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
        reader = csv.reader(stream, delimiter=delimiter)
        for line_number, row in enumerate(reader, start=1):
            if not row or all(not value.strip() for value in row):
                continue
            if line_number == 1 and _is_header(row):
                continue
            if len(row) != 3:
                yield line_number, ("", "", ""), False
                continue
            values = tuple(value.strip() for value in row)
            if not all(values):
                yield line_number, ("", "", ""), False
                continue
            contains_replacement = any("\ufffd" in value for value in values)
            yield line_number, values, contains_replacement


def read_existing_dataset(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "read_dataset"):
        if run.dataset not in DATASET_CONFIGS:
            raise ValueError(f"Unknown dataset key: {run.dataset}")

        config = DATASET_CONFIGS[run.dataset]
        available_sources: list[tuple[str, Path, str]] = []
        for split, filename, delimiter in config["sources"]:
            path = _source_path(run.project_root, run.dataset, filename)
            if path.is_file():
                available_sources.append((split, path, delimiter))
            else:
                _record_failure(
                    run,
                    "read_dataset",
                    "WARNING",
                    f"Declared local source file is absent: {path}",
                )
        if not available_sources:
            raise FileNotFoundError(
                f"No local source files were found for {run.dataset} under "
                f"{run.project_root / 'datasets'}"
            )

        official_splits = {split for split, _, _ in available_sources} >= {
            "train",
            "valid",
            "test",
        }
        if official_splits:
            split_limits = {
                "train": TRAIN_SAMPLE_SIZE,
                "valid": VALIDATION_SAMPLE_SIZE,
                "test": TEST_SAMPLE_SIZE,
            }
        else:
            split_limits = {available_sources[0][0]: SAMPLE_SIZE}
        rng = random.Random(SEED)
        reservoirs = {split: [] for split in split_limits}
        split_seen = Counter()
        split_statistics: list[dict[str, Any]] = []
        unique_triples: set[tuple[str, str, str]] = set()
        subjects: set[str] = set()
        predicates: set[str] = set()
        objects: set[str] = set()
        total_rows = 0
        malformed_rows = 0
        replacement_rows = 0

        for split, path, delimiter in available_sources:
            split_rows = 0
            split_malformed = 0
            split_replacements = 0
            for _, triple, has_replacement in _iter_source_rows(path, delimiter):
                if not all(triple):
                    malformed_rows += 1
                    split_malformed += 1
                    continue
                total_rows += 1
                split_rows += 1
                if has_replacement:
                    replacement_rows += 1
                    split_replacements += 1

                subject, predicate, object_ = (
                    sys.intern(value) for value in triple
                )
                canonical = (subject, predicate, object_)
                unique_triples.add(canonical)
                subjects.add(subject)
                predicates.add(predicate)
                objects.add(object_)

                if split in reservoirs:
                    split_seen[split] += 1
                    reservoir = reservoirs[split]
                    limit = split_limits[split]
                    if len(reservoir) < limit:
                        reservoir.append(canonical)
                    else:
                        replacement_index = rng.randrange(split_seen[split])
                        if replacement_index < limit:
                            reservoir[replacement_index] = canonical

            split_statistics.append(
                {
                    "split": split,
                    "source_file": str(path.relative_to(run.project_root)),
                    "file_bytes": path.stat().st_size,
                    "rows": split_rows,
                    "malformed_rows": split_malformed,
                    "rows_with_replacement_character": split_replacements,
                }
            )
            if split_malformed:
                _record_failure(
                    run,
                    "read_dataset",
                    "WARNING",
                    f"{split_malformed} malformed non-triple row(s) were excluded "
                    f"from {path.name}.",
                )
            if split_replacements:
                _record_failure(
                    run,
                    "read_dataset",
                    "WARNING",
                    f"{split_replacements} row(s) in {path.name} contain the "
                    "Unicode replacement character after UTF-8 decoding; the "
                    "visible value was preserved and is flagged.",
                )

        if not any(reservoirs.values()):
            raise ValueError(f"No valid triples were read for {run.dataset}")

        if official_splits:
            run.splits = {
                split: reservoirs[split]
                for split in ("train", "valid", "test")
            }
            sampling_method = "reservoir sampling within existing official splits"
        else:
            source_split = next(iter(reservoirs))
            selected = reservoirs[source_split]
            random.Random(SEED + 1).shuffle(selected)
            train_end = min(TRAIN_SAMPLE_SIZE, len(selected))
            valid_end = train_end + min(
                VALIDATION_SAMPLE_SIZE,
                max(0, len(selected) - train_end),
            )
            run.splits = {
                "train": selected[:train_end],
                "valid": selected[train_end:valid_end],
                "test": selected[valid_end:],
            }
            sampling_method = (
                "reservoir sample followed by deterministic 80/10/10 split"
            )
        run.sampled_triples = [
            triple for split in ("train", "valid", "test")
            for triple in run.splits.get(split, [])
        ]
        selected_split = (
            "official train/valid/test partitions"
            if official_splits
            else "single-file deterministic 80/10/10"
        )
        run.source_statistics = {
            "dataset": run.dataset,
            "software_environment": _software_environment(),
            "dataset_directory": str(
                (run.project_root / "datasets" / config["directory"]).relative_to(
                    run.project_root
                )
            ),
            "source_files": split_statistics,
            "sampling_source_split": selected_split,
            "sampling_method": sampling_method,
            "sampled_split_sizes": {
                split: len(triples) for split, triples in run.splits.items()
            },
            "sampling_source_triples": sum(split_seen.values()),
            "total_valid_source_rows": total_rows,
            "unique_source_triples": len(unique_triples),
            "repeated_source_rows": total_rows - len(unique_triples),
            "malformed_rows_excluded": malformed_rows,
            "rows_with_replacement_character": replacement_rows,
            "distinct_subject_terms": len(subjects),
            "distinct_predicate_terms": len(predicates),
            "distinct_object_terms": len(objects),
            "seed": SEED,
            "requested_sample_size": SAMPLE_SIZE,
        }
        return {
            "dataset": run.dataset,
            "source_files_found": [item["source_file"] for item in split_statistics],
            "sampling_source_split": selected_split,
            "source_rows_read": total_rows,
        }


def dataset_statistics(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "dataset_statistics"):
        if not run.source_statistics:
            raise RuntimeError("Read Existing Dataset must run before Dataset Statistics.")
        return run.source_statistics


def controlled_sampling(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "controlled_sampling"):
        if not run.sampled_triples:
            raise RuntimeError("Read Existing Dataset must run before Controlled Sampling.")
        return {
            "dataset": run.dataset,
            "seed": SEED,
            "sampling_method": "uniform reservoir sample without replacement",
            "sampling_source_split": run.source_statistics["sampling_source_split"],
            "requested_sample_size": SAMPLE_SIZE,
            "sampled_rows_before_deduplication": len(run.sampled_triples),
            "sampled_split_sizes": {
                split: len(triples) for split, triples in run.splits.items()
            },
            "calibration_queries_per_category": CALIB_QUERIES,
            "evaluation_queries_per_category": EVAL_QUERIES,
        }


def preprocessing(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "preprocessing"):
        train = sorted(set(run.splits.get("train", [])))
        if not train:
            raise ValueError(f"Preprocessing yielded no triples for {run.dataset}")
        seen = set(train)
        clean_splits = {"train": train}
        removed_leakage = 0
        for split in ("valid", "test"):
            clean_split = sorted(set(run.splits.get(split, [])) - seen)
            removed_leakage += len(run.splits.get(split, [])) - len(clean_split)
            seen.update(clean_split)
            clean_splits[split] = clean_split
        run.splits = clean_splits
        run.sampled_triples = [
            triple
            for split in ("train", "valid", "test")
            for triple in run.splits[split]
        ]
        run.clean_triples = train
        return {
            "sampled_unique_triples": len(run.sampled_triples),
            "training_triples": len(train),
            "calibration_triples": len(clean_splits["valid"]),
            "evaluation_triples": len(clean_splits["test"]),
            "overlap_removed_between_splits": removed_leakage,
            "term_normalization": "surrounding whitespace and UTF-8 BOM removed",
            "literal_representation": "source lexical value preserved as xsd:string",
        }


def _stable_name(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]}"


def _is_literal(value: str, dataset: str | None = None) -> bool:
    stripped = value.strip()
    if dataset == "WN18RR" and re.fullmatch(r"\d{8}", stripped):
        return False
    return bool(
        stripped.startswith('"')
        or stripped.startswith("'")
        or "^^" in stripped
        or re.fullmatch(r"[+-]?\d+(?:\.\d+)?", stripped)
        or stripped.lower() in {"true", "false"}
        or DATE_PATTERN.fullmatch(stripped)
    )


def construct_ontology(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "ontology_construction"):
        if not run.clean_triples:
            raise RuntimeError("Preprocessing must run before OWL Ontology Construction.")

        dataset_slug = re.sub(r"[^A-Za-z0-9_-]+", "_", run.dataset)
        ontology_iri = f"http://example.org/hermit-validation/{dataset_slug}/"
        ontology = get_ontology(ontology_iri)
        properties: dict[tuple[str, str], Any] = {}
        individuals: dict[str, Any] = {}
        object_assertions = 0
        data_assertions = 0

        with ontology:
            class KGEntity(Thing):
                pass

            for _, predicate, object_ in run.clean_triples:
                property_kind = (
                    "data" if _is_literal(object_, run.dataset) else "object"
                )
                property_key = (predicate, property_kind)
                if property_key not in properties:
                    name = _stable_name(
                        "dp" if property_kind == "data" else "op", predicate
                    )
                    base = DataProperty if property_kind == "data" else ObjectProperty
                    prop = types.new_class(name, (base,))
                    prop.label.append(predicate)
                    properties[property_key] = prop

            def get_individual(source_iri: str) -> Any:
                if source_iri not in individuals:
                    entity = KGEntity(
                        _stable_name("e", source_iri),
                        namespace=ontology,
                    )
                    entity.label.append(source_iri)
                    individuals[source_iri] = entity
                return individuals[source_iri]

            for subject, _, object_ in run.clean_triples:
                subject_individual = get_individual(subject)
                if not _is_literal(object_, run.dataset):
                    object_individual = get_individual(object_)
            for subject, predicate, object_ in run.clean_triples:
                subject_individual = get_individual(subject)
                property_kind = (
                    "data" if _is_literal(object_, run.dataset) else "object"
                )
                prop = properties[(predicate, property_kind)]
                if property_kind == "data":
                    getattr(subject_individual, prop.python_name).append(object_)
                    data_assertions += 1
                else:
                    object_individual = get_individual(object_)
                    getattr(subject_individual, prop.python_name).append(object_individual)
                    object_assertions += 1

        output_dir = run.project_root / "results" / run.dataset.replace("-", "")
        ontology_dir = output_dir / "ontology"
        ontology_dir.mkdir(parents=True, exist_ok=True)
        run.results_dir = output_dir
        run.ontology = ontology
        run.entity_individuals = individuals
        run.relation_properties = {
            predicate: prop
            for (predicate, kind), prop in properties.items()
            if kind == "object"
        }
        run.ontology_path = ontology_dir / "clean_ground_truth.owl"
        ontology.save(file=str(run.ontology_path), format="rdfxml")

        run.ontology_statistics = {
            "dataset": run.dataset,
            "source_triples_in_clean_sample": len(run.clean_triples),
            "owl_classes": 1,
            "named_individuals": len(individuals),
            "object_properties": sum(
                1 for _, kind in properties if kind == "object"
            ),
            "data_properties": sum(1 for _, kind in properties if kind == "data"),
            "object_property_assertions": object_assertions,
            "data_property_assertions": data_assertions,
            "explicit_domain_axioms": 0,
            "explicit_range_axioms": 0,
            "explicit_disjointness_axioms": 0,
            "source_schema_axioms_loaded": 0,
            "axiom_policy": (
                "Clean source ontology contains sampled assertions and "
                "KGEntity/property declarations only. Training-signature domain "
                "and range constraints are added later for the controlled "
                "benchmark and are separately documented as experimental."
            ),
            "owl_file": str(run.ontology_path.relative_to(run.project_root)),
        }
        return run.ontology_statistics


def clean_ground_truth(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "clean_ground_truth"):
        if not run.clean_triples or run.results_dir is None:
            raise RuntimeError(
                "Preprocessing and OWL Ontology Construction must run first."
            )
        output_path = run.results_dir / "clean_ground_truth.tsv"
        with output_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
            writer.writerow(("subject", "predicate", "object"))
            writer.writerows(run.clean_triples)
        split_files = {}
        for split in ("valid", "test"):
            split_path = run.results_dir / f"{split}_sample.tsv"
            with split_path.open(
                "w", encoding="utf-8", newline=""
            ) as stream:
                writer = csv.writer(
                    stream, delimiter="\t", lineterminator="\n"
                )
                writer.writerow(("subject", "predicate", "object"))
                writer.writerows(run.splits[split])
            split_files[split] = str(split_path.relative_to(run.project_root))
        return {
            "clean_ground_truth_triples": len(run.clean_triples),
            "validation_triples": len(run.splits["valid"]),
            "test_triples": len(run.splits["test"]),
            "file": str(output_path.relative_to(run.project_root)),
            "holdout_files": split_files,
        }


def _format_assertion(triple: tuple[str, str, str]) -> str:
    return json.dumps(list(triple), ensure_ascii=False)


def _relation_profiles(
    triples: list[tuple[str, str, str]],
    dataset: str,
) -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    subjects: dict[str, set[str]] = defaultdict(set)
    objects: dict[str, set[str]] = defaultdict(set)
    relations_by_entity: dict[str, set[str]] = defaultdict(set)
    for subject, predicate, object_ in triples:
        if _is_literal(object_, dataset):
            continue
        subjects[predicate].add(subject)
        objects[predicate].add(object_)
        relations_by_entity[subject].add(predicate)
        relations_by_entity[object_].add(predicate)
    return subjects, objects, relations_by_entity


def _make_labelled_pool(
    run: ExperimentRun,
    category: str,
    tag: str,
    positive_source: list[tuple[str, str, str]],
    train: list[tuple[str, str, str]],
    known_facts: set[tuple[str, str, str]],
    train_entities: list[str],
    subjects: dict[str, set[str]],
    objects: dict[str, set[str]],
    relations_by_entity: dict[str, set[str]],
    seed: int,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    positives = [
        triple
        for triple in positive_source
        if not _is_literal(triple[2], run.dataset)
        and triple[0] in relations_by_entity
        and triple[2] in relations_by_entity
        and triple[1] in run.relation_properties
    ]
    rng.shuffle(positives)
    positives = positives[: CALIB_QUERIES if tag == "calibration" else EVAL_QUERIES]

    negatives: list[tuple[tuple[str, str, str], tuple[str, str, str]]] = []
    negative_seen: set[tuple[str, str, str]] = set()
    attempts = 0
    target = len(positives)
    while len(negatives) < target and attempts < max(500, target * 100):
        attempts += 1
        if not train:
            break
        original = train[rng.randrange(len(train))]
        subject, predicate, object_ = original
        if predicate not in run.relation_properties or _is_literal(
            object_, run.dataset
        ):
            continue

        if category in {"Domain", "Missing Relation"}:
            alternatives = [
                entity for entity in train_entities
                if entity != subject
                and (
                    category == "Missing Relation"
                    or entity not in subjects.get(predicate, set())
                )
            ]
            if not alternatives:
                continue
            modified = (
                alternatives[rng.randrange(len(alternatives))],
                predicate,
                object_,
            )
        elif category in {"Range", "Duplicate Fact"}:
            alternatives = [
                entity for entity in train_entities
                if entity != object_
                and entity not in objects.get(predicate, set())
            ]
            if not alternatives:
                continue
            modified = (
                subject,
                predicate,
                alternatives[rng.randrange(len(alternatives))],
            )
        elif category == "Entity Type":
            replace_subject = rng.random() < 0.5
            reference = subject if replace_subject else object_
            alternatives = [
                entity for entity in train_entities
                if entity != reference
                and not (
                    relations_by_entity.get(entity, set())
                    & relations_by_entity.get(reference, set())
                )
            ]
            if not alternatives:
                continue
            replacement = alternatives[rng.randrange(len(alternatives))]
            modified = (
                (replacement, predicate, object_)
                if replace_subject
                else (subject, predicate, replacement)
            )
        else:
            raise ValueError(f"No HermiT benchmark injector for {category}")

        if modified in known_facts or modified in negative_seen:
            continue
        negative_seen.add(modified)
        negatives.append((original, modified))

    case_rows: list[dict[str, Any]] = []
    reason = (
        "Controlled benchmark: source-positive facts are held-out training-"
        "partition examples (or known training facts for near-duplicate tests); "
        "negative labels are assigned to generated corruption by construction. "
        "HermiT evaluates consistency against training-derived empirical relation "
        "signatures, which are experimental closed-world constraints, not "
        "authoritative ontology semantics."
    )
    if category == "Duplicate Fact":
        reason += (
            " This mirrors the reference pipeline's near-duplicate-tail protocol; "
            "OWL itself cannot distinguish repeated copies of an identical axiom."
        )
    if category == "Missing Relation":
        reason += (
            " The task is held-out link-candidate compatibility, not proof that an "
            "absent triple is false under OWL's Open World Assumption."
        )

    for label, original, modified in [
        (1, positive, positive) for positive in positives
    ] + [
        (0, original, modified) for original, modified in negatives
    ]:
        case_id = f"{run.dataset}-{category}-{tag}-{len(case_rows) + 1:04d}"
        case_class_name = _stable_name("Case", case_id)
        case_rows.append(
            {
                "dataset": run.dataset,
                "case_id": case_id,
                "error_category": category,
                "split": tag,
                "original_assertion": _format_assertion(original),
                "modified_assertion": _format_assertion(modified),
                "ground_truth": (
                    "Valid source fact" if label == 1 else "Injected corruption"
                ),
                "class_label": 0 if label == 1 else 1,
                "applicability": "Applicable (synthetic benchmark)",
                "methodological_reason": reason,
                "validation_prediction": "Pending HermiT classification",
                "reasoner_scope": (
                    "HermiT tests satisfiability of a named case class equivalent "
                    "to {subject} and hasValue(relation, object); an unsatisfiable "
                    "case class is predicted as an error."
                ),
                "_case_class_name": case_class_name,
                "_tag": tag,
                "_label": 0 if label == 1 else 1,
            }
        )
    return case_rows


def controlled_error_injection(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "controlled_error_injection"):
        if not run.clean_triples or not run.splits:
            raise RuntimeError("Clean Ground Truth must run before Error Injection.")
        train = run.splits["train"]
        valid = run.splits["valid"]
        test = run.splits["test"]
        subjects, objects, relations_by_entity = _relation_profiles(
            train, run.dataset
        )
        train_entities = sorted(relations_by_entity)
        known_facts = set(train) | set(valid) | set(test)

        run.cases = []
        run.calibration_cases = []
        run.applicability = []
        run.case_classes = {}

        supported = (
            "Domain",
            "Range",
            "Duplicate Fact",
            "Missing Relation",
        )
        duplicate_train = train.copy()
        random.Random(SEED + 23).shuffle(duplicate_train)
        duplicate_cal = duplicate_train[:CALIB_QUERIES]
        duplicate_eval = duplicate_train[CALIB_QUERIES : CALIB_QUERIES + EVAL_QUERIES]

        for category in supported:
            for tag, positives in (
                ("calibration", duplicate_cal if category == "Duplicate Fact" else valid),
                ("evaluation", duplicate_eval if category == "Duplicate Fact" else test),
            ):
                generated = _make_labelled_pool(
                    run,
                    category,
                    tag,
                    positives,
                    train,
                    known_facts,
                    train_entities,
                    subjects,
                    objects,
                    relations_by_entity,
                    SEED + (0 if tag == "calibration" else 1),
                )
                target = (
                    run.calibration_cases if tag == "calibration" else run.cases
                )
                target.extend(generated)

        not_applicable_reasons = {
            "Entity Type": (
                "N/A: this is a source-evidence limitation, not a HermiT "
                "capability limitation. HermiT can detect a type conflict when "
                "the ontology explicitly asserts incompatible types and declares "
                "their classes disjoint. These dataset files do not provide "
                "independently validated entity-type assertions and disjointness "
                "axioms. Inventing those labels or axioms from the same triples "
                "would make the evaluation circular, so no entity-type cases or "
                "classification metrics are reported."
            ),
            "Cross-KG Conflict": (
                "N/A: a single dataset is evaluated per notebook, and no "
                "independently validated cross-KG entity alignment is supplied."
            ),
            "Temporal/Contextual": (
                "N/A: local triples do not provide validated temporal qualifiers, "
                "context labels, or temporal truth rules."
            ),
        }
        representative = train[0]
        for category, reason in not_applicable_reasons.items():
            run.cases.append(
                {
                    "dataset": run.dataset,
                    "case_id": f"{run.dataset}-{category}-N-A",
                    "error_category": category,
                    "split": "evaluation",
                    "original_assertion": _format_assertion(representative),
                    "modified_assertion": "N/A (required source evidence unavailable)",
                    "ground_truth": "N/A",
                    "class_label": "N/A",
                    "prediction_score": "N/A",
                    "applicability": "N/A",
                    "methodological_reason": reason,
                    "validation_prediction": "N/A",
                    "reasoner_scope": "Not evaluated.",
                    "_tag": "evaluation",
                }
            )

        all_case_rows = run.calibration_cases + [
            row for row in run.cases if row["ground_truth"] != "N/A"
        ]
        with run.ontology:
            domain_classes: dict[str, tuple[Any, Any]] = {}
            range_classes: dict[str, tuple[Any, Any]] = {}
            candidate_relations = {
                json.loads(row["modified_assertion"])[1]
                for row in all_case_rows
            }
            for relation in sorted(candidate_relations):
                relation_key = _stable_name("r", relation)
                domain_allowed = types.new_class(
                    f"DomainAllowed_{relation_key}", (Thing,)
                )
                domain_unobserved = types.new_class(
                    f"DomainUnobserved_{relation_key}", (Thing,)
                )
                range_allowed = types.new_class(
                    f"RangeAllowed_{relation_key}", (Thing,)
                )
                range_unobserved = types.new_class(
                    f"RangeUnobserved_{relation_key}", (Thing,)
                )
                AllDisjoint([domain_allowed, domain_unobserved])
                AllDisjoint([range_allowed, range_unobserved])
                run.relation_properties[relation].domain = [domain_allowed]
                run.relation_properties[relation].range = [range_allowed]
                domain_classes[relation] = (
                    domain_allowed,
                    domain_unobserved,
                )
                range_classes[relation] = (range_allowed, range_unobserved)

            signature_memberships: set[tuple[str, str, str]] = set()

            for row in all_case_rows:
                subject, predicate, object_ = json.loads(row["modified_assertion"])
                if predicate not in run.relation_properties:
                    raise ValueError(
                        f"Candidate predicate has no object property: {predicate}"
                    )
                domain_allowed, domain_unobserved = domain_classes[predicate]
                range_allowed, range_unobserved = range_classes[predicate]
                for entity, allowed, unobserved, observed_entities, role in (
                    (
                        subject,
                        domain_allowed,
                        domain_unobserved,
                        subjects.get(predicate, set()),
                        "domain",
                    ),
                    (
                        object_,
                        range_allowed,
                        range_unobserved,
                        objects.get(predicate, set()),
                        "range",
                    ),
                ):
                    membership = (entity, predicate, role)
                    if membership in signature_memberships:
                        continue
                    signature_class = (
                        allowed if entity in observed_entities else unobserved
                    )
                    run.entity_individuals[entity].is_a.append(signature_class)
                    signature_memberships.add(membership)

                case_class = types.new_class(
                    row["_case_class_name"], (Thing,)
                )
                case_class.equivalent_to.append(
                    OneOf([run.entity_individuals[subject]])
                    & run.relation_properties[predicate].value(
                        run.entity_individuals[object_]
                    )
                )
                run.case_classes[row["case_id"]] = case_class

        case_ontology_path = (
            run.results_dir / "ontology" / "validation_cases.owl"
        )
        run.ontology.save(file=str(case_ontology_path), format="rdfxml")
        run.ontology_statistics.update(
            {
                "experimental_domain_axioms": sum(
                    relation in domain_classes
                    for relation in run.relation_properties
                ),
                "experimental_range_axioms": sum(
                    relation in range_classes
                    for relation in run.relation_properties
                ),
                "experimental_signature_membership_assertions": len(
                    signature_memberships
                ),
                "calibration_case_classes": len(run.calibration_cases),
                "evaluation_case_classes": len(
                    [row for row in run.cases if row["ground_truth"] != "N/A"]
                ),
                "schema_method": (
                    "Training-sample relation signatures encoded as disjoint "
                    "observed/unobserved domain and range classes, with explicit "
                    "candidate-entity membership assertions. These are empirical "
                    "closed-world benchmark constraints, not authoritative source "
                    "schema."
                ),
                "validation_cases_owl_file": str(
                    case_ontology_path.relative_to(run.project_root)
                ),
            }
        )

        for category in ERROR_CATEGORIES:
            cat_cases = [
                row for row in run.cases if row["error_category"] == category
            ]
            applicable_cases = [
                row for row in cat_cases if row["ground_truth"] != "N/A"
            ]
            reason = (
                applicable_cases[0]["methodological_reason"]
                if applicable_cases
                else not_applicable_reasons.get(
                    category, "No applicable labelled cases could be generated."
                )
            )
            run.applicability.append(
                {
                    "dataset": run.dataset,
                    "error_category": category,
                    "applicability": (
                        "Applicable (synthetic benchmark)"
                        if applicable_cases
                        else "N/A"
                    ),
                    "methodological_reason": reason,
                }
            )

        _write_dict_csv(
            run.results_dir / "case_level_results.csv",
            CASE_COLUMNS,
            [
                {key: value for key, value in row.items() if not key.startswith("_")}
                for row in run.cases
            ],
        )
        _write_dict_csv(
            run.results_dir / "calibration_cases.csv",
            CASE_COLUMNS,
            [
                {key: value for key, value in row.items() if not key.startswith("_")}
                for row in run.calibration_cases
            ],
        )
        _write_dict_csv(
            run.results_dir / "applicability_matrix.csv",
            APPLICABILITY_COLUMNS,
            run.applicability,
        )
        return {
            "calibration_cases": len(run.calibration_cases),
            "evaluation_cases": len(
                [row for row in run.cases if row["ground_truth"] != "N/A"]
            ),
            "labelled_categories": list(supported),
            "not_applicable_categories": list(not_applicable_reasons),
            "reasoner_batching": (
                "Each candidate is a named class-equivalent satisfiability test; "
                "HermiT classifies all independent cases in one run."
            ),
        }


def hermit_reasoning(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "hermit_reasoning"):
        if run.ontology is None or run.ontology_path is None:
            raise RuntimeError("OWL Ontology Construction must run before reasoning.")
        started = time.perf_counter()
        candidate_count = sum(
            row["ground_truth"] != "N/A"
            for row in run.calibration_cases + run.cases
        )
        heartbeat_stop = threading.Event()

        def report_heartbeat() -> None:
            while not heartbeat_stop.wait(30):
                elapsed = time.perf_counter() - started
                minutes, seconds = divmod(int(elapsed), 60)
                print(
                    f"HermiT is still reasoning over {candidate_count:,} "
                    f"candidate cases; elapsed {minutes}m {seconds:02d}s. "
                    "HermiT does not provide percentage progress.",
                    flush=True,
                )

        print(
            f"Starting HermiT reasoning over {candidate_count:,} candidate "
            "cases. Progress will be reported every 30 seconds.",
            flush=True,
        )
        heartbeat = threading.Thread(
            target=report_heartbeat,
            name="hermit-progress",
            daemon=True,
        )
        heartbeat.start()
        try:
            try:
                with _hermit_temp_workspace(run.project_root):
                    sync_reasoner([run.ontology], debug=0)
            except OwlReadyInconsistentOntologyError:
                run.reasoner_result = "INCONSISTENT"
            else:
                run.reasoner_result = "CONSISTENT"
        finally:
            heartbeat_stop.set()
            heartbeat.join()
        run.reasoner_runtime = round(time.perf_counter() - started, 6)
        print(
            f"HermiT reasoning finished: {run.reasoner_result} in "
            f"{run.reasoner_runtime:.1f}s.",
            flush=True,
        )
        if run.reasoner_result == "CONSISTENT":
            nothing = run.ontology.world[
                "http://www.w3.org/2002/07/owl#Nothing"
            ]
            for row in run.calibration_cases + run.cases:
                if row["ground_truth"] == "N/A":
                    continue
                case_class = run.case_classes[row["case_id"]]
                predicted_error = (
                    nothing in case_class.equivalent_to
                    or nothing in case_class.ancestors()
                )
                row["_prediction"] = int(predicted_error)
                row["prediction_score"] = int(predicted_error)
        else:
            _record_failure(
                run,
                "hermit_reasoning",
                "ERROR",
                "The combined training-signature ontology is inconsistent; "
                "per-case satisfiability predictions are unavailable.",
            )
        reasoned_path = run.results_dir / "ontology" / "hermit_reasoned.owl"
        run.ontology.save(file=str(reasoned_path), format="rdfxml")
        return {
            "reasoner": "HermiT (via Owlready2 sync_reasoner)",
            "reasoner_result": run.reasoner_result,
            "reasoner_runtime_seconds": run.reasoner_runtime,
            "reasoned_ontology_file": str(
                reasoned_path.relative_to(run.project_root)
            ),
            "scope": (
                "One HermiT classification run tests satisfiability for independent "
                "candidate classes over a training-derived signature ontology."
            ),
        }


def validation_prediction(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "validation_prediction"):
        if run.reasoner_result == "NOT_RUN":
            raise RuntimeError("HermiT Reasoning must run before Validation Prediction.")
        for row in run.calibration_cases + run.cases:
            if row["ground_truth"] == "N/A":
                continue
            if "_prediction" not in row:
                row["validation_prediction"] = "N/A (HermiT did not classify case)"
                continue
            row["validation_prediction"] = (
                "Error" if row["_prediction"] else "Valid"
            )

        for filename, rows in (
            ("case_level_results.csv", run.cases),
            ("calibration_cases.csv", run.calibration_cases),
        ):
            _write_dict_csv(
                run.results_dir / filename,
                CASE_COLUMNS,
                [
                    {
                        key: value for key, value in row.items()
                        if not key.startswith("_")
                    }
                    for row in rows
                ],
            )
        return {
            "clean_ontology_prediction": run.reasoner_result,
            "candidate_cases_classified": sum(
                "_prediction" in row
                for row in run.calibration_cases + run.cases
            ),
            "evaluation_predictions": Counter(
                row["validation_prediction"]
                for row in run.cases
                if row["ground_truth"] != "N/A"
            ),
            "explanation": (
                "An unsatisfiable candidate class is predicted as an error; a "
                "satisfiable candidate class is predicted as valid. This is a "
                "controlled benchmark using empirical training signatures, not "
                "authoritative source schema."
            ),
        }


def calculate_metrics(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "metrics"):
        if not run.cases:
            raise RuntimeError("Controlled Error Injection must run before metrics.")
        run.metrics = []
        evaluation_by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for case in run.cases:
            evaluation_by_category[case["error_category"]].append(case)

        all_labeled_queries = sum(
            row["ground_truth"] != "N/A"
            for row in run.calibration_cases + run.cases
        )
        average_case_runtime = (
            run.reasoner_runtime / all_labeled_queries
            if run.reasoner_runtime is not None and all_labeled_queries
            else "N/A"
        )

        for category in ERROR_CATEGORIES:
            category_cases = [
                row for row in evaluation_by_category.get(category, [])
                if row["ground_truth"] != "N/A"
            ]
            cases = [row for row in category_cases if "_prediction" in row]
            if not cases:
                run.metrics.append(
                    {
                        "Dataset": run.dataset,
                        "Error Category": category,
                        "Cases": "N/A",
                        "TP": "N/A",
                        "TN": "N/A",
                        "FP": "N/A",
                        "FN": "N/A",
                        "Accuracy": "N/A",
                        "Precision": "N/A",
                        "Recall": "N/A",
                        "F1": "N/A",
                        "Detection Rate": "N/A",
                        "Avg Runtime": "N/A",
                        "Median Runtime": "N/A",
                        "Best Error": "N/A",
                        "Coverage": "N/A",
                        "ROC-AUC": "N/A",
                        "Threshold": "N/A",
                        "N_queries": "N/A",
                        "N_found": "N/A",
                        "MRR": "N/A",
                        "Hits@1": "N/A",
                        "Hits@3": "N/A",
                        "Hits@10": "N/A",
                        "Runtime_seconds": "N/A",
                        "Positive Class": "N/A",
                        "Applicability": "N/A",
                        "Protocol": "N/A",
                        "Notes": (
                            "N/A: no supported source evidence or eligible labelled "
                            "cases for this category."
                        ),
                    }
                )
                continue

            tp = sum(
                row["_label"] == 1 and row["_prediction"] == 1 for row in cases
            )
            tn = sum(
                row["_label"] == 0 and row["_prediction"] == 0 for row in cases
            )
            fp = sum(
                row["_label"] == 0 and row["_prediction"] == 1 for row in cases
            )
            fn = sum(
                row["_label"] == 1 and row["_prediction"] == 0 for row in cases
            )
            n = len(category_cases)
            classified = len(cases)
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if precision + recall
                else 0.0
            )
            accuracy = (tp + tn) / classified
            specificity = tn / (tn + fp) if tn + fp else 0.0
            auc = (recall + specificity) / 2
            coverage = classified / n
            n_found = sum(row["_prediction"] == 1 for row in cases)
            applicable_row = next(
                row for row in run.applicability
                if row["error_category"] == category
            )
            run.metrics.append(
                {
                    "Dataset": run.dataset,
                    "Error Category": category,
                    "Cases": n,
                    "TP": tp,
                    "TN": tn,
                    "FP": fp,
                    "FN": fn,
                    "Accuracy": accuracy,
                    "Precision": precision,
                    "Recall": recall,
                    "F1": f1,
                    "Detection Rate": recall,
                    "Avg Runtime": average_case_runtime,
                    "Median Runtime": (
                        "N/A (one batch timing; no per-case samples)"
                    ),
                    "Best Error": "Pending",
                    "Coverage": coverage,
                    "ROC-AUC": auc,
                    "Threshold": 0.5,
                    "N_queries": n,
                    "N_found": n_found,
                    "MRR": "N/A (HermiT does not rank candidates)",
                    "Hits@1": "N/A (HermiT does not rank candidates)",
                    "Hits@3": "N/A (HermiT does not rank candidates)",
                    "Hits@10": "N/A (HermiT does not rank candidates)",
                    "Runtime_seconds": run.reasoner_runtime,
                    "Positive Class": "Injected corruption detected",
                    "Applicability": applicable_row["applicability"],
                    "Protocol": f"train_signature_{category.lower().replace(' ', '_')}",
                    "Notes": (
                        "Classification metrics use injected corruption as class 1. "
                        "Candidate labels are by construction; relation signatures "
                        "are empirical closed-world constraints, not authoritative "
                        "ontology facts. Threshold=0.5 maps satisfiable to valid, "
                        "unsatisfiable to error."
                    ),
                }
            )

        applicable_metrics = [
            row for row in run.metrics if isinstance(row["F1"], (int, float))
        ]
        best = max(applicable_metrics, key=lambda row: row["F1"]) if applicable_metrics else None
        for metric in applicable_metrics:
            metric["Best Error"] = (
                "Yes" if best and metric["Error Category"] == best["Error Category"]
                else "No"
            )

        return {
            "metric_rows": len(run.metrics),
            "scored_categories": sum(
                isinstance(row["F1"], (int, float)) for row in run.metrics
            ),
            "not_applicable_categories": [
                row["Error Category"]
                for row in run.metrics
                if row["F1"] == "N/A"
            ],
            "positive_class": "injected corruption detected",
            "metrics_rows": len(run.metrics),
        }


def runtime_analysis(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "runtime_analysis"):
        if run.reasoner_runtime is None:
            raise RuntimeError("HermiT Reasoning must run before Runtime Analysis.")
        total = round(time.perf_counter() - run.started_at, 6)
        result = {
            "dataset": run.dataset,
            "reasoner": "HermiT",
            "reasoner_runtime_seconds": run.reasoner_runtime,
            "pipeline_runtime_seconds_so_far": total,
            "stage_runtime_seconds": dict(run.timings),
            "category_specific_runtime": {
                category: "N/A" for category in ERROR_CATEGORIES
            },
        }
        return result


def _write_dict_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _dataset_summary(run: ExperimentRun) -> dict[str, Any]:
    return {
        **run.source_statistics,
        "dataset": run.dataset,
        "sampled_unique_triples": len(run.sampled_triples),
        "hermit_result": run.reasoner_result,
        "hermit_runtime_seconds": run.reasoner_runtime,
        "scored_error_categories": sum(
            isinstance(row["F1"], (int, float)) for row in run.metrics
        ),
        "all_category_metrics": "See overall_metrics.csv; unsupported categories are N/A",
    }


def export_results(run: ExperimentRun) -> dict[str, Any]:
    with _timed(run, "export_results"):
        if run.results_dir is None:
            raise RuntimeError("Experiment output directory is not initialized.")
        summary = _dataset_summary(run)
        summary_path = run.results_dir / "dataset_summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        ontology_stats_path = run.results_dir / "ontology_statistics.json"
        ontology_stats_path.write_text(
            json.dumps(run.ontology_statistics, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        metrics_path = run.results_dir / "overall_metrics.csv"
        _write_dict_csv(metrics_path, OVERALL_COLUMNS, [
            {
                **metric,
                "Source Triples": run.source_statistics["total_valid_source_rows"],
                "Sampled Triples": len(run.sampled_triples),
                "Ontology Individuals": run.ontology_statistics.get(
                    "named_individuals", "N/A"
                ),
                "Clean KG HermiT Result": run.reasoner_result,
                "Clean KG HermiT Runtime (seconds)": run.reasoner_runtime,
            }
            for metric in run.metrics
        ])
        runtime_path = run.results_dir / "runtime_analysis.json"
        runtime_path.write_text(
            json.dumps(
                {
                    "dataset": run.dataset,
                    "reasoner_runtime_seconds": run.reasoner_runtime,
                    "stage_runtime_seconds": run.timings,
                    "category_specific_runtime": {
                        category: "N/A" for category in ERROR_CATEGORIES
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        failure_path = run.results_dir / "failures_logs.csv"
        _write_dict_csv(failure_path, FAILURE_COLUMNS, run.failures)
        log_path = run.results_dir / "experiment_log.json"
        log_path.write_text(
            json.dumps(
                {
                    "dataset": run.dataset,
                    "status": "completed",
                    "reasoner_result": run.reasoner_result,
                    "failures_and_warnings": run.failures,
                    "timings": run.timings,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        master_path = build_master_workbook(run.project_root)
        return {
            "dataset": run.dataset,
            "result_directory": str(run.results_dir.relative_to(run.project_root)),
            "master_workbook": str(master_path.relative_to(run.project_root)),
            "master_workbook_updated": True,
            "saved_files": [
                str(path.relative_to(run.project_root))
                for path in (
                    summary_path,
                    ontology_stats_path,
                    metrics_path,
                    runtime_path,
                    failure_path,
                    log_path,
                    run.results_dir / "case_level_results.csv",
                    run.results_dir / "calibration_cases.csv",
                    run.results_dir / "applicability_matrix.csv",
                    run.results_dir / "clean_ground_truth.tsv",
                    run.ontology_path,
                    run.results_dir / "ontology" / "validation_cases.owl",
                    run.results_dir / "ontology" / "hermit_reasoned.owl",
                )
                if path is not None and path.is_file()
            ],
        }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _write_excel_sheet(workbook: Workbook, name: str, headers: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    worksheet = workbook.create_sheet(name)
    worksheet.append(list(headers))
    for cell in worksheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
    for row in rows:
        values = []
        for header in headers:
            value = row.get(header, "N/A")
            if isinstance(value, (dict, list, tuple)):
                value = json.dumps(value, ensure_ascii=False)
            values.append(value)
        worksheet.append(values)
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for column in worksheet.columns:
        cells = list(column)
        width = min(
            70,
            max(
                len(str(cell.value or ""))
                for cell in cells
            )
            + 2,
        )
        worksheet.column_dimensions[cells[0].column_letter].width = max(12, width)


def _excel_metric_value(header: str, value: Any) -> Any:
    numeric_columns = {
        "Cases",
        "TP",
        "TN",
        "FP",
        "FN",
        "Accuracy",
        "Precision",
        "Recall",
        "F1",
        "Detection Rate",
        "Coverage",
        "ROC-AUC",
        "Threshold",
        "N_queries",
        "N_found",
        "Runtime_seconds",
        "Avg Runtime",
        "Source Triples",
        "Sampled Triples",
        "Ontology Individuals",
        "Clean KG HermiT Runtime (seconds)",
    }
    if header not in numeric_columns or value in (None, "", "N/A"):
        return value if value not in (None, "") else "N/A"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() and header not in {
        "Accuracy", "Precision", "Recall", "F1", "Detection Rate", "Coverage",
        "ROC-AUC", "Threshold", "Avg Runtime",
        "Clean KG HermiT Runtime (seconds)",
    } else number


def build_master_workbook(
    project_root: Path, output_filename: str = "HermiT_Master_Results.xlsx"
) -> Path:
    root = Path(project_root).resolve()
    results_root = root / "results"
    summaries: list[dict[str, Any]] = []
    ontology_rows: list[dict[str, Any]] = []
    applicability_rows: list[dict[str, Any]] = []
    case_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    runtime_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []

    for dataset in DATASET_CONFIGS:
        result_dir = results_root / dataset.replace("-", "")
        required = (
            result_dir / "dataset_summary.json",
            result_dir / "ontology_statistics.json",
            result_dir / "case_level_results.csv",
            result_dir / "applicability_matrix.csv",
            result_dir / "overall_metrics.csv",
            result_dir / "runtime_analysis.json",
            result_dir / "failures_logs.csv",
        )
        if not all(path.is_file() for path in required):
            continue

        summary = _read_json(required[0])
        summaries.append(summary)
        ontology_statistics = _read_json(required[1])
        ontology_rows.append(ontology_statistics)
        dataset_cases = _read_csv(required[2])
        for row in dataset_cases:
            case_rows.append(row)
        applicability_rows.extend(_read_csv(required[3]))
        dataset_metrics = _read_csv(required[4])
        runtime = _read_json(required[5])
        for metric in dataset_metrics:
            row = {
                **metric,
                "Source Triples": summary["total_valid_source_rows"],
                "Sampled Triples": summary["sampled_unique_triples"],
                "Ontology Individuals": ontology_statistics["named_individuals"],
                "Clean KG HermiT Result": summary["hermit_result"],
                "Clean KG HermiT Runtime (seconds)": runtime[
                    "reasoner_runtime_seconds"
                ],
            }
            metric_rows.append(
                {
                    key: _excel_metric_value(key, value)
                    for key, value in row.items()
                }
            )
        runtime_rows.append(
            {
                "Dataset": dataset,
                "HermiT Runtime (seconds)": runtime["reasoner_runtime_seconds"],
                "Stage Runtime (seconds)": json.dumps(
                    runtime["stage_runtime_seconds"], ensure_ascii=False
                ),
                "Category Runtime": "Shared HermiT classification batch",
            }
        )
        failure_rows.extend(_read_csv(required[6]))

    if not summaries:
        raise FileNotFoundError(
            "No completed dataset results are available to publish to Excel."
        )

    workbook = Workbook()
    workbook.remove(workbook.active)
    _write_excel_sheet(
        workbook,
        "Dataset_Summary",
        tuple(summaries[0].keys()),
        summaries,
    )
    _write_excel_sheet(
        workbook,
        "Ontology_Statistics",
        tuple(ontology_rows[0].keys()),
        ontology_rows,
    )
    _write_excel_sheet(
        workbook,
        "Applicability_Matrix",
        APPLICABILITY_COLUMNS,
        applicability_rows,
    )
    _write_excel_sheet(workbook, "Case_Level_Results", CASE_COLUMNS, case_rows)
    _write_excel_sheet(workbook, "Overall_Metrics", OVERALL_COLUMNS, metric_rows)
    _write_excel_sheet(
        workbook,
        "Runtime_Analysis",
        (
            "Dataset",
            "HermiT Runtime (seconds)",
            "Stage Runtime (seconds)",
            "Category Runtime",
        ),
        runtime_rows,
    )
    _write_excel_sheet(workbook, "Failures_Logs", FAILURE_COLUMNS, failure_rows)

    output_path = root / output_filename
    workbook.save(output_path)
    return output_path


def _format_seconds(value: Any) -> str:
    if value is None or value == "N/A":
        return "N/A"
    return f"{float(value):.6f}"


def generate_thesis_report(
    project_root: Path, master_filename: str = "HermiT_Master_Results.xlsx"
) -> Path:
    root = Path(project_root).resolve()
    results_root = root / "results"
    summaries = [
        _read_json(
            results_root / dataset.replace("-", "") / "dataset_summary.json"
        )
        for dataset in DATASET_CONFIGS
    ]
    ontology_statistics = [
        _read_json(
            results_root / dataset.replace("-", "") / "ontology_statistics.json"
        )
        for dataset in DATASET_CONFIGS
    ]
    runtime_statistics = [
        _read_json(results_root / dataset.replace("-", "") / "runtime_analysis.json")
        for dataset in DATASET_CONFIGS
    ]
    applicability = [
        row
        for dataset in DATASET_CONFIGS
        for row in _read_csv(
            results_root / dataset.replace("-", "") / "applicability_matrix.csv"
        )
    ]
    measured_metrics = [
        row
        for dataset in DATASET_CONFIGS
        for row in _read_csv(
            results_root / dataset.replace("-", "") / "overall_metrics.csv"
        )
    ]

    dataset_table = [
        "| Dataset | Source files | Source rows | Unique source triples | Sample triples | HermiT consistency | HermiT runtime (s) |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    for summary, runtime in zip(summaries, runtime_statistics):
        source_files = ", ".join(item["source_file"] for item in summary["source_files"])
        dataset_table.append(
            f"| {summary['dataset']} | `{source_files}` | "
            f"{summary['total_valid_source_rows']} | "
            f"{summary['unique_source_triples']} | "
            f"{summary['sampled_unique_triples']} | "
            f"{summary['hermit_result']} | "
            f"{_format_seconds(runtime['reasoner_runtime_seconds'])} |"
        )
    software = summaries[0]["software_environment"]

    ontology_table = [
        "| Dataset | Individuals | Object properties | Data properties | Object assertions | Data assertions |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for stats in ontology_statistics:
        ontology_table.append(
            f"| {stats['dataset']} | {stats['named_individuals']} | "
            f"{stats['object_properties']} | {stats['data_properties']} | "
            f"{stats['object_property_assertions']} | {stats['data_property_assertions']} |"
        )

    applicability_table = [
        "| Dataset | Error category | Applicability | Methodological reason |",
        "|---|---|---|---|",
    ]
    for row in applicability:
        reason = row["methodological_reason"].replace("|", "\\|").replace("\n", " ")
        applicability_table.append(
            f"| {row['dataset']} | {row['error_category']} | "
            f"{row['applicability']} | {reason} |"
        )

    metric_table = [
        "| Dataset | Error category | Cases | TP | TN | FP | FN | Accuracy | Precision | Recall | F1 | ROC-AUC | Runtime (s) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in measured_metrics:
        metric_table.append(
            "| " + " | ".join(
                str(row.get(column, "N/A"))
                for column in (
                    "Dataset", "Error Category", "Cases", "TP", "TN", "FP",
                    "FN", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC",
                    "Runtime_seconds",
                )
            ) + " |"
        )

    report = f"""# Ontology-Based Knowledge Graph Validation with HermiT

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
- Software versions: HermiT `{software['hermit']}`, Owlready2
  `{software['owlready2']}`, Java `{software['java']}`, Python
  `{software['python']}`.
- Random seed: `{SEED}`.
- Controlled sample: up to `{SAMPLE_SIZE}` triples per dataset (up to
  `{TRAIN_SAMPLE_SIZE}` train, `{VALIDATION_SAMPLE_SIZE}` validation, and
  `{TEST_SAMPLE_SIZE}` test triples), with seed `{SEED}`; official local splits
  are preserved where available. No download occurs.
- Data acquisition: none. Only the files already present under `datasets/`
  are read.
- Each notebook uses the shared `hermit_validation.py` pipeline. Notebook cell
  layout, functions, parameters, outputs, and evaluation logic are identical;
  the dataset key (and consequently its local file path) is the only difference.
- The benchmark uses held-out source assertions as valid candidates and
  relation-signature corruptions as injected-error candidates; calibration and
  evaluation pools are capped at `{CALIB_QUERIES}` and `{EVAL_QUERIES}` per
  applicable category, respectively. This smaller sample and case pool reduces
  runtime and statistical power; report results as a controlled sample benchmark,
  not as full-dataset performance or real-world error detection absent an
  external oracle.

## Dataset-wise results

{chr(10).join(dataset_table)}

The table reports clean sampled-ontology consistency and the measured HermiT
runtime; category classification results appear below. Runtime is elapsed wall
time on this machine and is not a general performance estimate.

## Ontology construction statistics

{chr(10).join(ontology_table)}

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

{chr(10).join(metric_table)}

`ROC-AUC` is the binary-score AUC (equivalent here to balanced accuracy).
`MRR`/`Hits@K` are N/A because HermiT does not rank candidates. Cross-KG
conflict and temporal/contextual metrics are N/A because the local inputs lack
validated entity alignment and temporal/context labels/rules. The workbook's
`Overall_Metrics` sheet contains the dataset/category aggregates; individual
candidate assertions and predictions are in `Case_Level_Results`.

## Applicability and limitations

{chr(10).join(applicability_table)}

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

- Master workbook: `{master_filename}` (category candidate details are included
  in `Overall_Metrics`; no separate category tabs are generated)
- Executed dataset notebooks: `01_Wikidata_HermiT.ipynb` through
  `05_YAGO3-10_HermiT.ipynb`
- Results directory: `results/`
- Dependency manifest: `requirements.txt`
- Shared implementation: `hermit_validation.py`
- Notebook factory/runner: `create_notebooks.py`, `run_experiments.py`
"""
    output_path = root / "HermiT_Thesis_Report.md"
    output_path.write_text(report, encoding="utf-8")
    return output_path


def build_master_outputs(
    project_root: Path, master_filename: str = "HermiT_Master_Results.xlsx"
) -> dict[str, str]:
    workbook_path = build_master_workbook(project_root, master_filename)
    report_path = generate_thesis_report(project_root, master_filename)
    return {
        "master_excel": str(workbook_path),
        "thesis_report": str(report_path),
    }


def run_experiment(dataset: str, project_root: Path) -> ExperimentRun:
    """Run the complete validation pipeline for one configured dataset."""
    run = ExperimentRun(dataset, project_root.resolve())
    stages = (
        read_existing_dataset,
        dataset_statistics,
        controlled_sampling,
        preprocessing,
        construct_ontology,
        clean_ground_truth,
        controlled_error_injection,
        hermit_reasoning,
        validation_prediction,
        calculate_metrics,
        runtime_analysis,
        export_results,
    )
    for stage in stages:
        result = stage(run)
        print(f"  {stage.__name__}: {json.dumps(result, ensure_ascii=False, default=str)}")
    return run


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the HermiT validation pipeline over the local five-dataset "
            "collection."
        )
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=tuple(DATASET_CONFIGS),
        default=list(DATASET_CONFIGS),
        metavar="DATASET",
        help=(
            "Datasets to run (default: all five): "
            + ", ".join(DATASET_CONFIGS)
        ),
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent

    print("HermiT knowledge-graph validation")
    print(f"Project: {project_root}")
    print(f"Datasets: {', '.join(args.datasets)}")
    print("Running HermiT sanity check...")
    print(json.dumps(run_toy_sanity(project_root), ensure_ascii=False, indent=2))

    for dataset in args.datasets:
        print(f"\n=== {dataset} ===")
        run_experiment(dataset, project_root)

    outputs = build_master_outputs(project_root)
    print("\nAll requested datasets completed.")
    print(f"Master workbook: {outputs['master_excel']}")
    print(f"Thesis report: {outputs['thesis_report']}")


if __name__ == "__main__":
    main()
