#!/usr/bin/env python3
"""Validate links across extraction, library and sequencing component files."""

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from referencing.exceptions import Unresolvable

from validate_schemas import SCHEMA_DIR, check_schemas, read_json, validate_document


@dataclass
class LinkReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_provenance(extractions, libraries, sequencing, collections=None, require_complete=False):
    """Check one note's component files, without inferring missing links.

    Missing links are warnings for legacy records, or errors in complete mode.
    Supplied dangling, duplicate or conflicting identifiers are always errors.
    Collection records are optional; when supplied, sample links are checked too.
    """
    report = LinkReport()
    documents = [
        ("extractions", extractions, "04_extraction_methods_schema.json"),
        ("libraries", libraries, "05_library_prep_methods_schema.json"),
        ("sequencing", sequencing, "06_sequencing_data_schema.json"),
    ]
    if collections is not None:
        documents.extend((f"collection[{i}]", doc, "03_collection_schema.json") for i, doc in enumerate(collections))
    for label, document, schema in documents:
        report.errors.extend(f"{label}{message}" for message in validate_document(document, SCHEMA_DIR / schema))
    if report.errors:
        return report

    def missing(message):
        (report.errors if require_complete else report.warnings).append(message)

    def records(document, group_key, record_key, label):
        for group_index, group in enumerate(document.get("methods", {}).get(group_key, [])):
            for index, record in enumerate(group.get(record_key, [])):
                yield f"{label}/methods/{group_key}/{group_index}/{record_key}/{index}", record

    extraction_rows = list(records(extractions, "sample_processing", "nucleic_acid_extraction", "extractions"))
    library_rows = list(records(libraries, "library_prep", "library_preparation_and_sequencing", "libraries"))
    run_rows = [
        (view, path, record)
        for view in ("library_sequencing", "raw_data")
        for path, record in records(sequencing, "sample_processing", view, "sequencing")
    ]
    for name, rows in (("extraction", extraction_rows), ("library", library_rows), ("sequencing run", run_rows)):
        if not rows:
            missing(f"No {name} records supplied; this part of the provenance chain cannot be checked")

    def index_rows(rows, key):
        indexed = {}
        for path, record in rows:
            value = record.get(key)
            if not value or not value.strip():
                missing(f"{path}/{key}: missing identifier; provenance is incomplete")
            elif value in indexed:
                report.errors.append(f"{path}/{key}: duplicate identifier {value!r} (first at {indexed[value][0]})")
            else:
                indexed[value] = (path, record)
        return indexed

    extraction_ids = index_rows(extraction_rows, "extraction_id")
    library_ids = index_rows(library_rows, "library_id")
    sample_ids = None
    if collections is not None:
        sample_ids = index_rows([(f"collection[{i}]", record) for i, record in enumerate(collections)], "sample_accession")
        if not collections:
            missing("No collection records supplied; sample provenance cannot be checked")

    def check_sample(path, record):
        accession = record.get("sample_accession")
        if "sample_accession" in record and not accession.strip():
            missing(f"{path}/sample_accession: blank sample identifier; provenance is incomplete")
            return
        if sample_ids is not None and accession and accession not in sample_ids:
            report.errors.append(f"{path}/sample_accession: unknown collection sample {accession!r}")

    for path, record in extraction_rows:
        check_sample(path, record)
    for path, record in library_rows:
        check_sample(path, record)
        sources = record.get("source_extraction_ids")
        if not sources:
            missing(f"{path}/source_extraction_ids: source extraction is unknown; do not infer it from the BioSample")
        for source in sources or []:
            if source not in extraction_ids:
                report.errors.append(f"{path}/source_extraction_ids: unknown extraction {source!r}")

    runs_by_view = {}
    run_library = {}
    run_experiment = {}
    run_sample = {}
    experiment_library = {}
    for path, record in library_rows:
        experiment = record.get("experiment_accession")
        library_id = record.get("library_id")
        if experiment and library_id:
            previous = experiment_library.setdefault(experiment, library_id)
            if previous != library_id:
                report.errors.append(f"{path}/experiment_accession: experiment {experiment!r} is assigned to different libraries")

    for view, path, record in run_rows:
        check_sample(path, record)
        library_id = record.get("library_id")
        if not library_id:
            missing(f"{path}/library_id: missing library link; provenance is incomplete")
        elif library_id not in library_ids:
            report.errors.append(f"{path}/library_id: unknown library {library_id!r}")

        accession_key = "sequencing_accession" if view == "library_sequencing" else "run_accession"
        accession = record.get(accession_key)
        if not accession or not accession.strip():
            missing(f"{path}/{accession_key}: missing run identifier; provenance is incomplete")
        else:
            view_key = (view, accession)
            if view_key in runs_by_view:
                report.errors.append(f"{path}/{accession_key}: duplicate run {accession!r} in {view}")
            runs_by_view[view_key] = path
            if library_id:
                previous = run_library.setdefault(accession, library_id)
                if previous != library_id:
                    report.errors.append(f"{path}/library_id: run {accession!r} links to different libraries in the two sequencing views")
            for key, known in (("experiment_accession", run_experiment), ("sample_accession", run_sample)):
                value = record.get(key)
                if value and value.strip():
                    previous = known.setdefault(accession, value)
                    if previous != value:
                        report.errors.append(f"{path}/{key}: run {accession!r} has conflicting values {previous!r} and {value!r}")

        experiment = record.get("experiment_accession")
        if library_id in library_ids and experiment:
            # A physical library can be used by several archive experiments.
            # A repeated experiment must still refer to the same library.
            previous = experiment_library.setdefault(experiment, library_id)
            if previous != library_id:
                report.errors.append(f"{path}/experiment_accession: experiment belongs to library {previous!r}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extractions", type=Path, required=True, help="Schema 04 component file")
    parser.add_argument("--libraries", type=Path, required=True, help="Schema 05 component file")
    parser.add_argument("--sequencing", type=Path, required=True, help="Schema 06 component file")
    parser.add_argument("--collection", type=Path, nargs="+", help="Schema 03 file(s), one per BioSample")
    parser.add_argument("--require-complete", action="store_true", help="Treat missing provenance identifiers/links as errors")
    args = parser.parse_args()
    try:
        errors = check_schemas()
        if errors:
            parser.exit(1, "\n".join(errors) + "\n")
        report = validate_provenance(
            read_json(args.extractions), read_json(args.libraries), read_json(args.sequencing),
            collections=[read_json(path) for path in args.collection] if args.collection is not None else None,
            require_complete=args.require_complete,
        )
    except (OSError, ValueError, KeyError, Unresolvable) as error:
        parser.exit(1, f"Validation could not run: {error}\n")
    for message in report.warnings:
        print(f"WARNING: {message}")
    if report.errors:
        parser.exit(1, "\n".join(f"ERROR: {message}" for message in report.errors) + "\n")
    if report.warnings:
        print("No conflicting supplied links found; provenance is incomplete (see warnings).")
    else:
        print("Extraction-library-run links passed.")
    if args.collection is None:
        print("Collection sample links were not checked: no --collection files supplied.")


if __name__ == "__main__":
    main()
