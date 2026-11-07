"""Validation examples for references, contributors and sequencing records."""

import copy
import unittest
from pathlib import Path

from validate_schemas import load_validator


ROOT = Path(__file__).resolve().parents[1]


def person(role="preserver"):
    return {
        "role": [role],
        "email": "",
        "affiliations": [],
        "given_names": "Example",
        "surname": "Person",
        "orcid": "",
    }


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator(ROOT / "02_references_schema.json")

    def reference(self, **overrides):
        return {
            "title": "Example reference",
            "citation_key": "example",
            "authors": [],
            "entry_type": "book/chapter",
            **overrides,
        }

    def valid(self, reference):
        return self.validator.is_valid({"references": [reference]})

    def test_reference_needs_no_obsolete_fields_or_invented_identifier(self):
        self.assertTrue(self.valid(self.reference()))

    def test_existing_required_fields_are_still_required(self):
        for field in ("title", "citation_key", "authors", "entry_type"):
            with self.subTest(field=field):
                reference = self.reference()
                del reference[field]
                self.assertFalse(self.valid(reference))

    def test_dataset_requires_its_data_accession(self):
        reference = self.reference(entry_type="dataset")
        self.assertFalse(self.valid(reference))
        reference["data_accession"] = {
            "source": "GenBank",
            "accession": "GCA_123456789.1",
        }
        self.assertTrue(self.valid(reference))

    def test_non_dataset_does_not_accept_data_accession(self):
        reference = self.reference(
            entry_type="article",
            data_accession={"source": "GenBank", "accession": "GCA_123456789.1"},
        )
        self.assertFalse(self.valid(reference))

    def test_identifier_requires_both_format_and_value(self):
        for identifier in ({"format": "ISBN"}, {"value": "3161484100"}):
            with self.subTest(identifier=identifier):
                self.assertFalse(self.valid(self.reference(identifier=identifier)))

    def test_isbn_10_and_13_basic_formats(self):
        for value in (
            "3161484100",
            "3-16-148410-0",
            "0-8044-2957-X",
            "080442957x",
            "9783161484100",
            "978-3-16-148410-0",
            "979 1 2345 6789 6",
        ):
            with self.subTest(value=value):
                self.assertTrue(self.valid(self.reference(
                    identifier={"format": "ISBN", "value": value}
                )))

    def test_malformed_isbn_values_are_rejected(self):
        for value in (
            "NEED A PATTERN HERE TO VALIDATE",
            "978316148410",
            "97831614841000",
            "9773161484100",
            "3--16-148410-0",
            "ISBN 978-3-16-148410-0",
            "X161484100",
        ):
            with self.subTest(value=value):
                self.assertFalse(self.valid(self.reference(
                    identifier={"format": "ISBN", "value": value}
                )))

    def test_isbn_check_is_format_only(self):
        # The final digit differs from the valid 9783161484100 checksum.
        self.assertTrue(self.valid(self.reference(
            identifier={"format": "ISBN", "value": "9783161484101"}
        )))


class ContributorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        author = load_validator(ROOT / "_author_schema.json")
        cls.author_validator = author.evolve(schema=author.schema["$defs"]["author"])
        cls.collection_validator = load_validator(ROOT / "03_collection_schema.json")

    def test_preserver_is_a_valid_author_role(self):
        self.author_validator.validate(person())

    def test_collection_role_requires_gal_association(self):
        author = person("collection")
        self.assertFalse(self.author_validator.is_valid(author))
        author["gal_association"] = "Example GAL"
        self.author_validator.validate(author)

    def test_collector_is_not_silently_added_as_an_author_synonym(self):
        author = person("collector")
        author["gal_association"] = "Example GAL"
        self.assertFalse(self.author_validator.is_valid(author))

    def test_sample_roles_include_preserver_without_renaming_collector(self):
        sample = {
            "sample_accession": "SAMEA12345",
            "specimen_id": "SPECIMEN1",
            "organism_part": "whole organism",
            "involved_persons": [{
                "authorsdb_id": "1",
                "roles": ["collector", "identifier", "preserver"],
            }],
        }
        self.collection_validator.validate(sample)
        sample["involved_persons"][0]["roles"] = ["unrecognised_role"]
        self.assertFalse(self.collection_validator.is_valid(sample))


class ExtractionTests(unittest.TestCase):
    def test_ont_is_supported_at_both_extraction_levels(self):
        validator = load_validator(ROOT / "04_extraction_methods_schema.json")
        extraction = {
            "sample_role": "ont",
            "sample_accession": "SAMEA12345",
            "tissue_type": "whole organism",
        }
        document = {"methods": {
            "involved_persons": [person()],
            "sample_processing": [{
                "sample_role": "ont",
                "nucleic_acid_extraction": [extraction],
            }],
        }}
        validator.validate(document)
        extraction["sample_role"] = "unrecognised_role"
        self.assertFalse(validator.is_valid(document))


class SequencingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator(ROOT / "06_sequencing_data_schema.json")

    def document(self):
        return {"methods": {"sample_processing": [{
            "sample_role": "pacbio",
            "raw_data": [{
                "sample_accession": "SAMEA12345",
                "data_type": "pacbio_hifi",
                "run_accession": "ERR12345",
                "submitted_bytes": 10,
                "read_count": 5,
                "base_count_gb": 0.000005,
            }],
            "cumulative_raw_data_statistics": {
                "sequencing_portal_enrichment_applied": False,
                "cumulative_stats": [{
                    "read_count_unit": "reads",
                    "reads_in_millions": 0.000005,
                    "total_yield_mbp": 0.005,
                    "total_yield_gbp": 0.000005,
                }],
            },
        }]}}

    def test_raw_records_and_totals_validate_within_sample_role(self):
        self.validator.validate(self.document())

    def test_raw_counts_reject_negative_and_nonnumeric_values(self):
        for field in ("submitted_bytes", "read_count", "base_count_gb"):
            for value in (-1, "5"):
                with self.subTest(field=field, value=value):
                    document = self.document()
                    document["methods"]["sample_processing"][0]["raw_data"][0][field] = value
                    self.assertFalse(self.validator.is_valid(document))

    def test_cumulative_counts_reject_negative_and_nonnumeric_values(self):
        for field in ("reads_in_millions", "total_yield_mbp", "total_yield_gbp"):
            for value in (-1, "5"):
                with self.subTest(field=field, value=value):
                    document = self.document()
                    totals = document["methods"]["sample_processing"][0]["cumulative_raw_data_statistics"]
                    totals["cumulative_stats"][0][field] = value
                    self.assertFalse(self.validator.is_valid(document))

    def test_sequencing_containers_enforce_their_declared_types(self):
        for field, value in (("raw_data", {}), ("cumulative_raw_data_statistics", [])):
            with self.subTest(field=field):
                document = self.document()
                document["methods"]["sample_processing"][0][field] = value
                self.assertFalse(self.validator.is_valid(document))

    def test_multiple_role_groups_can_keep_separate_totals(self):
        document = self.document()
        second = copy.deepcopy(document["methods"]["sample_processing"][0])
        second["sample_role"] = "ont"
        second["raw_data"][0].update(data_type="ont", run_accession="ERR67890")
        document["methods"]["sample_processing"].append(second)
        self.validator.validate(document)


if __name__ == "__main__":
    unittest.main()
