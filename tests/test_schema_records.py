"""Regression tests for publication, assembly, analysis and annotation records."""

import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator


SCHEMA_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILES = {
    "metadata": "01_meta_data_schema.json",
    "assembly": "07_assembly_schema.json",
    "analysis": "09_analysis_schema.json",
    "annotation": "10_annotation_schema.json",
}


class SchemaRecordTests(unittest.TestCase):
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
        errors = list(self.validators[schema].iter_errors(instance))
        self.assertEqual([], [error.message for error in errors])

    def assert_invalid_at(self, schema, instance, path):
        errors = list(self.validators[schema].iter_errors(instance))
        self.assertTrue(
            any(list(error.absolute_path) == path for error in errors),
            f"Expected an error at {path!r}; got "
            f"{[(list(error.absolute_path), error.message) for error in errors]!r}",
        )

    @staticmethod
    def metadata_record():
        return {
            "metadata": {
                "doi": "10.1234/example",
                "title": "Example genome note",
                "bioproject": "PRJEB1",
                "authors": [],
                "affiliations": [],
                "data_availability": "Data are openly available.",
                "child_bioprojects": [],
                "parent_projects": [],
                "formatted_parent_projects": "Example project",
            },
            "publication_metadata": {
                "journal_data": [{"journal_name": "Example journal"}],
                "genome_note_data": {
                    "existing_genome_note": "https://example.org/note"
                },
                "ebp_analysis_metrics": [],
                "ethics_and_consent": "N/A",
                "competing_interests": "N/A",
            },
        }

    @staticmethod
    def assembly_record():
        return {
            "assembly_methods": {
                "assembly_method_text": "The assembly was generated and curated.",
                "organelle_assembly": [{
                    "organelle_type": "mitochondrion",
                    "assembler": {"name": "Example assembler", "ID": "tool1"},
                    "comparator": [{"name": "Example species", "accession": "GCA_2"}],
                }],
            },
            "assembly_stats": [{
                "assembly_information": {
                    "assembly_accession": "GCA_1",
                    "no_of_contigs": 1,
                    "contig_n50_length": 100,
                    "no_of_scaffolds": 1,
                    "scaffold_n50_length": 100,
                    "genome_size": 100,
                    "organelles": [{"name": "MT", "length_kb": 16, "gc_percent": 30}],
                },
                "assembly_analysis": {
                    "ploidy": {"count": 2, "method": {"software": "Example tool"}},
                    "kmer_analysis": [{"name": "genomescope", "est_size_bp": 100}],
                    "raw_data_object": [{"accession": "ERR1"}],
                    "taxonomy": [{"ncbi_taxonomy_id": "1"}],
                    "chromosome_tables": [{"chromosome": "1", "size_mb": 1}],
                },
            }],
        }

    @staticmethod
    def analysis_record():
        return {"analysis": [{
            "assembly_role": {"assembly": "Haplotype_1"},
            "ebp_statistics": {"ebp_qv_benchmark": 40},
            "GAP_analysis_data": {
                "readmapping": {
                    "workflow": "wf1", "aligned_reads": [{"accession": "ERR1"}]
                },
                "sequence_composition": [{"workflow": "wf2", "accession": "GCA_1"}],
                "blobtoolkit": {"workflow": "wf3", "snail_plot": "snail.png"},
                "ancestral_linkage_group": {"workflow": "wf4", "assembly_id": "assembly1"},
                "pretext": {"workflow": "wf5", "file_path": "example.pretext"},
                "higlass": {"workflow": "wf6", "mcool_file": "example.mcool"},
                "merqury": [{"workflow": "wf7", "qv": 40}],
                "busco": [{"workflow": "wf8", "complete_percent": 99}],
            },
        }]}

    @staticmethod
    def annotation_record():
        return {"annotation": [{
            "data_used": [{"accession": "ERR1"}],
            "statistics": {
                "total_gene_count": 10,
                "busco": {
                    "tool_version": "5.0",
                    "results": [{
                        "mode": "protein",
                        "lineages": {"odb_name": "metazoa_odb10", "complete": 99},
                    }],
                },
                "omark": {
                    "tool_version": "1.0",
                    "assessments": [{
                        "clades": {
                            "clade_name": "Metazoa",
                            "completeness": {"percentage": 99},
                        }
                    }],
                },
            },
        }]}

    def test_schemas_pass_draft_2020_12_meta_validation(self):
        for name, schema in self.schemas.items():
            with self.subTest(schema=name):
                Draft202012Validator.check_schema(schema)

    def test_metadata_record_is_valid(self):
        self.assert_valid("metadata", self.metadata_record())

    def test_journal_records_reject_primitive_items(self):
        for value in [None, 42, "journal"]:
            with self.subTest(value=value):
                record = self.metadata_record()
                record["publication_metadata"]["journal_data"] = [value]
                self.assert_invalid_at("metadata", record, ["publication_metadata", "journal_data", 0])

    def test_journal_fields_are_typed(self):
        for field in ["journal_name", "e_location_id", "license", "submission_date", "publication_date"]:
            with self.subTest(field=field):
                record = self.metadata_record()
                record["publication_metadata"]["journal_data"][0][field] = 42
                self.assert_invalid_at("metadata", record, ["publication_metadata", "journal_data", 0, field])

    def test_genome_note_metadata_requires_an_object(self):
        record = self.metadata_record()
        record["publication_metadata"]["genome_note_data"] = "not a record"
        self.assert_invalid_at("metadata", record, ["publication_metadata", "genome_note_data"])

    def test_genome_note_fields_are_typed(self):
        for field in ["existing_genome_note", "submission_date", "publication_date"]:
            with self.subTest(field=field):
                record = self.metadata_record()
                record["publication_metadata"]["genome_note_data"][field] = 42
                self.assert_invalid_at("metadata", record, ["publication_metadata", "genome_note_data", field])

    def test_assembly_information_and_analysis_share_a_record(self):
        self.assert_valid("assembly", self.assembly_record())

    def test_assembly_records_reject_primitive_items(self):
        for value in [None, 42, "assembly"]:
            with self.subTest(value=value):
                self.assert_invalid_at("assembly", {"assembly_stats": [value]}, ["assembly_stats", 0])

    def test_assembly_information_required_fields_are_enforced(self):
        record = self.assembly_record()
        del record["assembly_stats"][0]["assembly_information"]["assembly_accession"]
        self.assert_invalid_at("assembly", record, ["assembly_stats", 0, "assembly_information"])

    def test_organelle_bounds_and_types_are_enforced(self):
        for field, value in [("length_kb", -1), ("gc_percent", 101), ("accession", 42)]:
            with self.subTest(field=field):
                record = self.assembly_record()
                record["assembly_stats"][0]["assembly_information"]["organelles"][0][field] = value
                self.assert_invalid_at("assembly", record, ["assembly_stats", 0, "assembly_information", "organelles", 0, field])

    def test_organelle_comparators_are_object_records(self):
        record = self.assembly_record()
        record["assembly_methods"]["organelle_assembly"][0]["comparator"] = [42]
        self.assert_invalid_at("assembly", record, ["assembly_methods", "organelle_assembly", 0, "comparator", 0])

    def test_nested_assembly_analysis_shapes_are_enforced(self):
        replacements = {
            "ploidy": {"count": "two"},
            "kmer_analysis": [42],
            "raw_data_object": [42],
            "taxonomy": [{"ncbi_taxonomy_id": 1}],
        }
        suffixes = {"ploidy": ["count"], "kmer_analysis": [0], "raw_data_object": [0], "taxonomy": [0, "ncbi_taxonomy_id"]}
        for field, value in replacements.items():
            with self.subTest(field=field):
                record = self.assembly_record()
                record["assembly_stats"][0]["assembly_analysis"][field] = value
                self.assert_invalid_at("assembly", record, ["assembly_stats", 0, "assembly_analysis", field] + suffixes[field])

    def test_all_gap_analysis_components_are_valid(self):
        self.assert_valid("analysis", self.analysis_record())

    def test_analysis_records_reject_primitive_items(self):
        for value in [None, 42, "analysis"]:
            with self.subTest(value=value):
                self.assert_invalid_at("analysis", {"analysis": [value]}, ["analysis", 0])

    def test_gap_analysis_component_shapes_are_enforced(self):
        replacements = {"readmapping": [], "blobtoolkit": [], "pretext": [], "merqury": {}, "busco": {}, "sequence_composition": {}}
        for field, value in replacements.items():
            with self.subTest(field=field):
                record = self.analysis_record()
                record["analysis"][0]["GAP_analysis_data"][field] = value
                self.assert_invalid_at("analysis", record, ["analysis", 0, "GAP_analysis_data", field])

    def test_aligned_reads_are_object_records(self):
        record = self.analysis_record()
        record["analysis"][0]["GAP_analysis_data"]["readmapping"]["aligned_reads"] = [42]
        self.assert_invalid_at("analysis", record, ["analysis", 0, "GAP_analysis_data", "readmapping", "aligned_reads", 0])

    def test_workflow_identifiers_are_strings(self):
        baseline = self.analysis_record()
        for field, value in baseline["analysis"][0]["GAP_analysis_data"].items():
            with self.subTest(component=field):
                record = copy.deepcopy(baseline)
                component = record["analysis"][0]["GAP_analysis_data"][field]
                suffix = [0] if isinstance(value, list) else []
                target = component[0] if suffix else component
                target["workflow"] = 42
                self.assert_invalid_at("analysis", record, ["analysis", 0, "GAP_analysis_data", field] + suffix + ["workflow"])

    def test_analysis_numeric_bounds_are_enforced(self):
        for component, field, value in [("merqury", "qv", -1), ("merqury", "kmer_completeness_percent", 101), ("busco", "complete_percent", 101)]:
            with self.subTest(component=component, field=field):
                record = self.analysis_record()
                record["analysis"][0]["GAP_analysis_data"][component][0][field] = value
                self.assert_invalid_at("analysis", record, ["analysis", 0, "GAP_analysis_data", component, 0, field])
        record = self.analysis_record()
        record["analysis"][0]["ebp_statistics"]["ebp_qv_benchmark"] = -1
        self.assert_invalid_at("analysis", record, ["analysis", 0, "ebp_statistics", "ebp_qv_benchmark"])

    def test_assembly_role_retains_its_object_shape(self):
        record = self.analysis_record()
        record["analysis"][0]["assembly_role"] = "Haplotype_1"
        self.assert_invalid_at("analysis", record, ["analysis", 0, "assembly_role"])

    def test_annotation_record_is_valid(self):
        self.assert_valid("annotation", self.annotation_record())

    def test_annotation_records_reject_primitive_items(self):
        for value in [None, 42, "annotation"]:
            with self.subTest(value=value):
                self.assert_invalid_at("annotation", {"annotation": [value]}, ["annotation", 0])

    def test_annotation_inputs_are_object_records(self):
        record = self.annotation_record()
        record["annotation"][0]["data_used"] = [42]
        self.assert_invalid_at("annotation", record, ["annotation", 0, "data_used", 0])

    def test_annotation_busco_mode_is_required_per_result(self):
        record = self.annotation_record()
        del record["annotation"][0]["statistics"]["busco"]["results"][0]["mode"]
        self.assert_invalid_at("annotation", record, ["annotation", 0, "statistics", "busco", "results", 0])

    def test_annotation_statistics_and_lineage_types_are_enforced(self):
        record = self.annotation_record()
        record["annotation"][0]["statistics"]["total_gene_count"] = "ten"
        self.assert_invalid_at("annotation", record, ["annotation", 0, "statistics", "total_gene_count"])
        for value, suffix in [([], []), ({"complete": "ninety-nine"}, ["complete"])]:
            with self.subTest(lineages=value):
                record = self.annotation_record()
                record["annotation"][0]["statistics"]["busco"]["results"][0]["lineages"] = value
                self.assert_invalid_at("annotation", record, ["annotation", 0, "statistics", "busco", "results", 0, "lineages"] + suffix)

    def test_omark_clades_and_nested_percentages_are_enforced(self):
        for value, suffix in [([], []), ({"completeness": {"percentage": 101}}, ["completeness", "percentage"])]:
            with self.subTest(clades=value):
                record = self.annotation_record()
                record["annotation"][0]["statistics"]["omark"]["assessments"][0]["clades"] = value
                self.assert_invalid_at("annotation", record, ["annotation", 0, "statistics", "omark", "assessments", 0, "clades"] + suffix)


if __name__ == "__main__":
    unittest.main()
