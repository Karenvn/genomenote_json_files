"""Cross-component provenance checks for repeated extractions and libraries."""

import copy
import unittest

from validate_provenance import validate_provenance


def components():
    """Two independent extraction/library chains deliberately share a BioSample."""
    extraction_records = [
        {"extraction_id": extraction_id, "sample_accession": "SAMEA1", "tissue_type": "leaf"}
        for extraction_id in ("EXT1", "EXT2")
    ]
    library_records = [
        {
            "library_id": f"LIB{number}",
            "source_extraction_ids": [f"EXT{number}"],
            "sample_accession": "SAMEA1",
            "experiment_accession": f"ERX{number}",
            # Repeated names are allowed; explicit IDs carry the identity.
            "library_name": "Leaf DNA",
        }
        for number in (1, 2)
    ]
    raw_records = [
        {
            "library_id": f"LIB{number}",
            "sample_accession": "SAMEA1",
            "run_accession": f"ERR{number}",
            "experiment_accession": f"ERX{number}",
            "data_type": "pacbio_hifi",
        }
        for number in (1, 2)
    ]
    sequencing_records = [
        {
            "library_id": row["library_id"],
            "sample_accession": row["sample_accession"],
            "sequencing_accession": row["run_accession"],
            "experiment_accession": row["experiment_accession"],
            "sequencing_protocol": "sequencing_example",
            "sequencing_protocol_plaintext": "Example sequencing protocol.",
            "instrument_model": "PacBio Revio",
        }
        for row in raw_records
    ]
    return (
        {"methods": {"sample_processing": [{
            "sample_role": "pacbio", "nucleic_acid_extraction": extraction_records,
        }]}},
        {"methods": {"library_prep": [{
            "sample_role": "pacbio", "library_preparation_and_sequencing": library_records,
        }]}},
        {"methods": {"sample_processing": [{
            "sample_role": "pacbio", "raw_data": raw_records,
            "library_sequencing": sequencing_records,
        }]}},
    )


class ProvenanceIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.extractions, self.libraries, self.sequencing = components()
        self.extraction_rows = self.extractions["methods"]["sample_processing"][0]["nucleic_acid_extraction"]
        self.library_rows = self.libraries["methods"]["library_prep"][0]["library_preparation_and_sequencing"]
        self.sequencing_group = self.sequencing["methods"]["sample_processing"][0]
        self.raw_rows = self.sequencing_group["raw_data"]
        self.run_rows = self.sequencing_group["library_sequencing"]

    def validate(self, **kwargs):
        return validate_provenance(self.extractions, self.libraries, self.sequencing, **kwargs)

    def assert_valid(self, **kwargs):
        report = self.validate(**kwargs)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def assert_error(self, text, **kwargs):
        report = self.validate(**kwargs)
        self.assertTrue(any(text in message for message in report.errors), report)

    def test_distinct_extractions_and_libraries_can_share_sample_and_display_name(self):
        self.assert_valid(require_complete=True)

    def test_one_extraction_can_supply_several_libraries(self):
        self.library_rows[1]["source_extraction_ids"] = ["EXT1"]
        self.assert_valid(require_complete=True)

    def test_library_can_explicitly_pool_two_extractions(self):
        self.library_rows[1]["source_extraction_ids"] = ["EXT1", "EXT2"]
        self.assert_valid(require_complete=True)

    def test_one_library_can_have_several_runs_and_experiments(self):
        self.raw_rows[1]["library_id"] = "LIB1"
        self.raw_rows[1]["experiment_accession"] = "ERX3"
        self.run_rows[1]["library_id"] = "LIB1"
        self.run_rows[1]["experiment_accession"] = "ERX3"
        self.assert_valid(require_complete=True)

    def test_experiment_need_not_be_registered_on_library_record(self):
        del self.library_rows[0]["experiment_accession"]
        self.assert_valid(require_complete=True)

    def test_duplicate_extraction_id_is_rejected_across_role_groups(self):
        self.extractions["methods"]["sample_processing"].append({
            "sample_role": "hic",
            "nucleic_acid_extraction": [copy.deepcopy(self.extraction_rows[0])],
        })
        self.assert_error("duplicate identifier 'EXT1'")

    def test_duplicate_library_id_is_rejected(self):
        self.library_rows[1]["library_id"] = "LIB1"
        self.assert_error("duplicate identifier 'LIB1'")

    def test_dangling_extraction_link_is_rejected_despite_matching_sample(self):
        self.library_rows[0]["source_extraction_ids"] = ["EXT_MISSING"]
        self.assert_error("unknown extraction 'EXT_MISSING'")

    def test_dangling_library_link_is_rejected_in_either_sequencing_view(self):
        for rows in (self.raw_rows, self.run_rows):
            with self.subTest(view="raw_data" if rows is self.raw_rows else "library_sequencing"):
                rows[0]["library_id"] = "LIB_MISSING"
                self.assert_error("unknown library 'LIB_MISSING'")
                rows[0]["library_id"] = "LIB1"

    def test_same_sample_does_not_resolve_missing_extraction_link(self):
        del self.library_rows[0]["source_extraction_ids"]
        report = self.validate()
        self.assertEqual(report.errors, [])
        self.assertTrue(any("source_extraction_ids" in message for message in report.warnings), report)
        self.assert_error("source_extraction_ids", require_complete=True)

    def test_legacy_missing_ids_warn_and_fail_complete_mode(self):
        for row in self.extraction_rows:
            del row["extraction_id"]
        for row in self.library_rows:
            del row["library_id"]
            del row["source_extraction_ids"]
        for row in self.raw_rows + self.run_rows:
            del row["library_id"]
        report = self.validate()
        self.assertEqual(report.errors, [])
        self.assertTrue(report.warnings)
        report = self.validate(require_complete=True)
        self.assertTrue(report.errors)
        self.assertEqual(report.warnings, [])

    def test_empty_documents_cannot_claim_complete_provenance(self):
        report = validate_provenance({}, {}, {}, require_complete=True)
        self.assertEqual(len(report.errors), 3)
        self.assertEqual(report.warnings, [])
        for record_type in ("extraction", "library", "sequencing run"):
            self.assertTrue(any(f"No {record_type} records" in error for error in report.errors), report)

    def test_same_run_can_appear_once_in_each_sequencing_view(self):
        self.assert_valid(require_complete=True)

    def test_duplicate_run_within_either_view_is_rejected(self):
        for rows in (self.raw_rows, self.run_rows):
            with self.subTest(view="raw_data" if rows is self.raw_rows else "library_sequencing"):
                rows.append(copy.deepcopy(rows[0]))
                self.assert_error("duplicate run 'ERR1'")
                rows.pop()

    def test_same_run_cannot_link_to_two_libraries_across_views(self):
        self.run_rows[0]["library_id"] = "LIB2"
        self.assert_error("links to different libraries")

    def test_same_run_has_one_experiment_even_when_library_link_is_unknown(self):
        self.run_rows[0]["experiment_accession"] = "ERX_DIFFERENT"
        for linked in (True, False):
            with self.subTest(library_link_known=linked):
                if not linked:
                    del self.run_rows[0]["library_id"]
                    del self.raw_rows[0]["library_id"]
                report = self.validate()
                self.assertTrue(any(
                    "ERR1" in message and "experiment" in message
                    for message in report.errors
                ), report)

    def test_same_run_has_one_sample_even_without_collection_records(self):
        self.run_rows[0]["sample_accession"] = "SAMEA_OTHER"
        report = self.validate()
        self.assertTrue(any(
            "ERR1" in message and "sample" in message
            for message in report.errors
        ), report)

    def test_present_blank_samples_warn_or_fail_without_collection_records(self):
        for row in (self.extraction_rows[0], self.library_rows[0], self.raw_rows[0], self.run_rows[0]):
            for value in ("", "   "):
                with self.subTest(record=row, value=repr(value)):
                    row["sample_accession"] = value
                    report = self.validate()
                    self.assertEqual(report.errors, [])
                    self.assertTrue(any(
                        "sample_accession" in message for message in report.warnings
                    ), report)
                    self.assert_error("sample_accession", require_complete=True)
                    row["sample_accession"] = "SAMEA1"

    def test_absent_optional_library_and_raw_samples_remain_allowed(self):
        for row in self.library_rows + self.raw_rows:
            del row["sample_accession"]
        self.assert_valid(require_complete=True)

    def test_existing_experiment_cannot_be_reassigned_to_another_library(self):
        self.raw_rows[0]["experiment_accession"] = "ERX2"
        self.assert_error("experiment")

    def test_experiment_seen_only_in_runs_cannot_link_to_two_libraries(self):
        for row in self.library_rows:
            del row["experiment_accession"]
        for row in self.raw_rows + self.run_rows:
            row["experiment_accession"] = "ERX_SHARED"
        self.assert_error("experiment")

    def test_matching_optional_collection_resolves_sample_links(self):
        self.assert_valid(collections=[{
            "sample_accession": "SAMEA1", "specimen_id": "SPECIMEN1", "organism_part": "leaf",
        }], require_complete=True)

    def test_optional_collection_checks_samples_in_each_component(self):
        collection = {"sample_accession": "SAMEA1", "specimen_id": "SPECIMEN1", "organism_part": "leaf"}
        for row in (self.extraction_rows[0], self.library_rows[0], self.raw_rows[0], self.run_rows[0]):
            with self.subTest(record=row):
                row["sample_accession"] = "SAMEA_MISSING"
                self.assert_error("unknown collection sample 'SAMEA_MISSING'", collections=[collection])
                row["sample_accession"] = "SAMEA1"

    def test_duplicate_collection_sample_is_rejected(self):
        collection = {"sample_accession": "SAMEA1", "specimen_id": "SPECIMEN1", "organism_part": "leaf"}
        self.assert_error("duplicate identifier 'SAMEA1'", collections=[collection, copy.deepcopy(collection)])


if __name__ == "__main__":
    unittest.main()
