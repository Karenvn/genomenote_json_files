"""Schema checks for optional extraction-to-library-to-run links.

The repeated-extraction and pooled-library fixtures are synthetic. Cross-file
identifier uniqueness and reference resolution belong to the integrity checker.
"""

import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator


SCHEMA_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILES = {
    "extraction": "04_extraction_methods_schema.json",
    "library": "05_library_prep_methods_schema.json",
    "sequencing": "06_sequencing_data_schema.json",
}


class ProvenanceFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {
            name: json.loads((SCHEMA_ROOT / filename).read_text(encoding="utf-8"))
            for name, filename in SCHEMA_FILES.items()
        }
        cls.validators = {
            name: Draft202012Validator(schema)
            for name, schema in cls.schemas.items()
        }

    def assert_valid(self, schema, instance):
        self.assertEqual(
            [], [error.message for error in self.validators[schema].iter_errors(instance)]
        )

    def assert_invalid(self, schema, instance):
        self.assertTrue(list(self.validators[schema].iter_errors(instance)))

    @staticmethod
    def extraction_document(records):
        return {"methods": {"sample_processing": [{
            "sample_role": "pacbio", "nucleic_acid_extraction": records
        }]}}

    @staticmethod
    def library_document(records):
        return {"methods": {"library_prep": [{
            "sample_role": "pacbio", "library_preparation_and_sequencing": records
        }]}}

    @staticmethod
    def sequencing_document(records, field="library_sequencing"):
        return {"methods": {"sample_processing": [{
            "sample_role": "pacbio", field: records
        }]}}

    @staticmethod
    def extraction_record():
        return {"sample_accession": "SAMEA1", "tissue_type": "leaf"}

    @staticmethod
    def library_record():
        return {
            "sample_accession": "SAMEA1",
            "library_name": "A reusable display name",
            "experiment_accession": "ERX1",
        }

    @staticmethod
    def sequencing_record():
        return {
            "sample_accession": "SAMEA1",
            "sequencing_accession": "ERR1",
            "sequencing_protocol": "protocol1",
            "sequencing_protocol_plaintext": "Sequenced with the stated protocol.",
            "instrument_model": "Example instrument",
        }

    def test_schemas_pass_meta_validation(self):
        for name, schema in self.schemas.items():
            with self.subTest(schema=name):
                Draft202012Validator.check_schema(schema)

    def test_legacy_records_without_links_remain_valid(self):
        self.assert_valid(
            "extraction", self.extraction_document([self.extraction_record()])
        )
        self.assert_valid("library", self.library_document([self.library_record()]))
        self.assert_valid(
            "sequencing", self.sequencing_document([self.sequencing_record()])
        )
        self.assert_valid(
            "sequencing",
            self.sequencing_document(
                [{"sample_accession": "SAMEA1", "run_accession": "ERR1"}], "raw_data"
            ),
        )

    def test_one_sample_can_have_multiple_identified_extractions(self):
        records = [
            {**self.extraction_record(), "extraction_id": "extraction-1"},
            {**self.extraction_record(), "extraction_id": "extraction-2"},
        ]
        self.assert_valid("extraction", self.extraction_document(records))

    def test_library_can_link_one_or_multiple_pooled_extractions(self):
        for sources in [["extraction-1"], ["extraction-1", "extraction-2"]]:
            with self.subTest(sources=sources):
                record = {
                    **self.library_record(),
                    "library_id": "library-1",
                    "source_extraction_ids": sources,
                }
                self.assert_valid("library", self.library_document([record]))

    def test_an_extraction_can_supply_multiple_libraries(self):
        records = [
            {
                **self.library_record(),
                "library_id": "library-1",
                "source_extraction_ids": ["extraction-1"],
            },
            {
                **self.library_record(),
                "experiment_accession": "ERX2",
                "library_id": "library-2",
                "source_extraction_ids": ["extraction-1"],
            },
        ]
        self.assert_valid("library", self.library_document(records))

    def test_a_library_can_supply_multiple_public_runs(self):
        sequencing = [
            {
                **self.sequencing_record(),
                "library_id": "library-1",
                "experiment_accession": "ERX1",
            },
            {
                **self.sequencing_record(),
                "sequencing_accession": "ERR2",
                "library_id": "library-1",
                "experiment_accession": "ERX2",
            },
        ]
        self.assert_valid("sequencing", self.sequencing_document(sequencing))
        raw_data = [
            {"run_accession": "ERR1", "library_id": "library-1", "experiment_accession": "ERX1"},
            {"run_accession": "ERR2", "library_id": "library-1", "experiment_accession": "ERX2"},
        ]
        self.assert_valid("sequencing", self.sequencing_document(raw_data, "raw_data"))

    def test_run_experiment_accessions_are_optional_strings(self):
        for field in ["library_sequencing", "raw_data"]:
            baseline = self.sequencing_record() if field == "library_sequencing" else {"run_accession": "ERR1"}
            with self.subTest(field=field, case="omitted"):
                self.assert_valid("sequencing", self.sequencing_document([baseline], field))
            with self.subTest(field=field, case="known"):
                record = {**baseline, "experiment_accession": "ERX1"}
                self.assert_valid("sequencing", self.sequencing_document([record], field))
            for value in [42, None, ["ERX1", "ERX2"]]:
                with self.subTest(field=field, value=value):
                    record = {**baseline, "experiment_accession": value}
                    self.assert_invalid("sequencing", self.sequencing_document([record], field))

    def test_identifiers_reject_empty_whitespace_and_nonstring_values(self):
        cases = [
            ("extraction", self.extraction_document, self.extraction_record(), "extraction_id"),
            ("library", self.library_document, self.library_record(), "library_id"),
            ("sequencing", self.sequencing_document, self.sequencing_record(), "library_id"),
            (
                "sequencing",
                lambda records: self.sequencing_document(records, "raw_data"),
                {"run_accession": "ERR1"},
                "library_id",
            ),
        ]
        for schema, document, baseline, field in cases:
            for value in ["", " \t\n", None, 42, ["library-1"]]:
                with self.subTest(schema=schema, field=field, value=value):
                    record = {**baseline, field: value}
                    self.assert_invalid(schema, document([record]))

    def test_source_ids_reject_empty_duplicate_blank_and_nonstrings(self):
        invalid_sources = [
            [],
            ["extraction-1", "extraction-1"],
            [""],
            [" \t\n"],
            [None],
            [42],
            "extraction-1",
            None,
        ]
        for sources in invalid_sources:
            with self.subTest(sources=sources):
                record = {
                    **self.library_record(),
                    "library_id": "library-1",
                    "source_extraction_ids": sources,
                }
                self.assert_invalid("library", self.library_document([record]))

    def test_source_extraction_links_require_a_library_identifier(self):
        record = {
            **self.library_record(), "source_extraction_ids": ["extraction-1"]
        }
        self.assert_invalid("library", self.library_document([record]))
        record["library_id"] = "library-1"
        self.assert_valid("library", self.library_document([record]))

    def test_known_library_identity_does_not_require_guessing_extraction_links(self):
        record = {**self.library_record(), "library_id": "library-1"}
        self.assert_valid("library", self.library_document([record]))

    def test_public_runs_link_one_library_not_a_multiplexing_array(self):
        record = {**self.sequencing_record(), "library_id": "library-1"}
        self.assert_valid("sequencing", self.sequencing_document([record]))
        malformed = copy.deepcopy(record)
        malformed["library_id"] = ["library-1", "library-2"]
        self.assert_invalid("sequencing", self.sequencing_document([malformed]))
        raw_record = {"run_accession": "ERR1", "library_id": "library-1"}
        self.assert_valid("sequencing", self.sequencing_document([raw_record], "raw_data"))
        raw_record["library_id"] = ["library-1", "library-2"]
        self.assert_invalid("sequencing", self.sequencing_document([raw_record], "raw_data"))


if __name__ == "__main__":
    unittest.main()
