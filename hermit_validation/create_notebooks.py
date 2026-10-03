"""Create the five identical dataset notebooks used by the experiment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


NOTEBOOKS = (
    ("01_Wikidata_HermiT.ipynb", "Wikidata"),
    ("02_DBpedia_HermiT.ipynb", "DBpedia"),
    ("03_FB15K237_HermiT.ipynb", "FB15K-237"),
    ("04_WN18RR_HermiT.ipynb", "WN18RR"),
    ("05_YAGO3-10_HermiT.ipynb", "YAGO3-10"),
)

PIPELINE_CELLS = (
    ("Read Existing Dataset", "read_existing_dataset(run)"),
    ("Dataset Statistics", "dataset_statistics(run)"),
    ("Controlled Sampling", "controlled_sampling(run)"),
    ("Preprocessing", "preprocessing(run)"),
    ("OWL Ontology Construction", "construct_ontology(run)"),
    ("Clean Ground Truth", "clean_ground_truth(run)"),
    ("Controlled Error Injection", "controlled_error_injection(run)"),
    ("HermiT Reasoning", "hermit_reasoning(run)"),
    ("Validation Prediction", "validation_prediction(run)"),
    ("TP/TN/FP/FN and Metrics", "calculate_metrics(run)"),
    ("Runtime Analysis", "runtime_analysis(run)"),
    ("Export Results", "export_results(run)"),
)


def _markdown_cell(source: str, cell_id: str) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "id": cell_id,
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def _code_cell(source: str, cell_id: str) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": cell_id,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def notebook_document(dataset: str) -> dict[str, Any]:
    introduction = f"""# {dataset}: HermiT Knowledge Graph Validation

This notebook runs the shared OWL 2/HermiT pipeline over the local dataset
files. The only dataset-specific setting is `DATASET_KEY`; sampling, seed,
ontology construction, candidate mutations, evaluation rules, and output schema
are shared by all five notebooks.

The experiment uses at most 2,000 source triples per dataset (up to 1,600
training, 200 validation, and 200 test triples; seed 42). Official splits are
preserved when available; otherwise a deterministic train/validation/test split
is made. Each applicable category is capped at 50 calibration and 50 evaluation
queries. HermiT tests candidate-class satisfiability against training-derived
finite relation signatures. Metrics are for this reduced controlled benchmark,
not full-dataset performance or independently verified real-world errors;
entity type, cross-KG conflict, and temporal/contextual metrics are `N/A` where
the local files lack required semantic evidence.
"""
    cells = [
        _markdown_cell(introduction, "overview"),
        _code_cell(
            "import json\n"
            "from pathlib import Path\n"
            "from hermit_validation import (\n"
            "    ExperimentRun,\n"
            "    calculate_metrics,\n"
            "    clean_ground_truth,\n"
            "    construct_ontology,\n"
            "    controlled_error_injection,\n"
            "    controlled_sampling,\n"
            "    dataset_statistics,\n"
            "    export_results,\n"
            "    hermit_reasoning,\n"
            "    preprocessing,\n"
            "    read_existing_dataset,\n"
            "    runtime_analysis,\n"
            "    validation_prediction,\n"
            ")\n"
            f"DATASET_KEY = {dataset!r}\n"
            "PROJECT_ROOT = Path.cwd()\n"
            "run = ExperimentRun(DATASET_KEY, PROJECT_ROOT)\n"
            "def show(value):\n"
            "    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))\n"
            "print(f'Dataset: {DATASET_KEY}; seed: 42; sample cap: 2,000')\n",
            "configuration",
        ),
    ]
    for index, (title, call) in enumerate(PIPELINE_CELLS, start=1):
        cells.append(
            _markdown_cell(f"## {title}\n", f"stage-{index:02d}-heading")
        )
        cells.append(_code_cell(f"show({call})\n", f"stage-{index:02d}-run"))

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.14",
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def create_notebooks(project_root: Path) -> list[Path]:
    root = Path(project_root).resolve()
    paths = []
    for filename, dataset in NOTEBOOKS:
        path = root / filename
        path.write_text(
            json.dumps(notebook_document(dataset), indent=1, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        paths.append(path)
    return paths


if __name__ == "__main__":
    created = create_notebooks(Path(__file__).resolve().parent)
    for path in created:
        print(path)
