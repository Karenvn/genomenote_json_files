"""Repository checks and document-level rules beyond standard JSON Schema."""

import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from json_to_tsv_converter import FIELDNAMES, extract_schema_metadata, resolve_schema_refs
from validate_schemas import SCHEMA_DIR, check_schemas, lint_schema, validate_document


class ValidationTests(unittest.TestCase):
    def test_all_schemas_and_local_references(self):
        self.assertEqual([], check_schemas())

    def test_lint_catches_ignored_array_properties(self):
        schema = {"type": "array", "properties": {"value": {"type": "number"}}}
        self.assertTrue(any("applies to objects" in e for e in lint_schema(schema)))

    def test_lint_catches_misplaced_nested_fields(self):
        schema = {"type": "object", "raw_data": {"type": "array"}}
        self.assertTrue(any("/raw_data" in e for e in lint_schema(schema)))

    def test_annotations_and_instance_data_are_not_linted_as_schemas(self):
        schema = {
            "type": "object", "help": "Example", "recommended": True,
            "source": ["manifest"], "examples": [{"raw_data": 3}],
            "default": {"unrelated_key": 1}, "const": {"another_key": 2},
        }
        self.assertEqual([], lint_schema(schema))

    def test_open_arrays_and_conditional_object_constraints_remain_valid(self):
        self.assertEqual([], lint_schema({"type": "array"}))
        self.assertEqual([], lint_schema({"if": {"properties": {"mode": {"const": "x"}}}}))
        self.assertEqual([], lint_schema({"type": ["array", "object"], "properties": {}, "items": {}}))

    def test_meta_check_catches_shorthand_and_boolean_required(self):
        for schema in (
            {"type": "object", "properties": {"journal_name": "string"}},
            {"type": "object", "required": True},
        ):
            with self.subTest(schema=schema), tempfile.TemporaryDirectory() as directory:
                Path(directory, "01_test_schema.json").write_text(json.dumps(schema), encoding="utf-8")
                self.assertTrue(check_schemas(directory))

    def test_broken_references_are_detected_without_retrieval(self):
        for ref in ("_missing_schema.json#/$defs/author", "https://example.invalid/schema"):
            with self.subTest(ref=ref), tempfile.TemporaryDirectory() as directory:
                schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": ref}
                Path(directory, "01_test_schema.json").write_text(json.dumps(schema), encoding="utf-8")
                self.assertTrue(any("unresolved $ref" in e for e in check_schemas(directory)))

    def test_malformed_schema_metadata_is_reported_before_resource_loading(self):
        for schema in ({"$schema": 42}, {"$id": 42}):
            with self.subTest(schema=schema), tempfile.TemporaryDirectory() as directory:
                Path(directory, "01_test_schema.json").write_text(json.dumps(schema), encoding="utf-8")
                errors = check_schemas(directory)
                self.assertTrue(any("not of type 'string'" in e for e in errors))

    def test_reference_keys_are_unique_but_titles_may_repeat(self):
        reference = {"title": "Repeated title", "authors": [], "entry_type": "article"}
        data = {"references": [{**reference, "citation_key": "first"}, {**reference, "citation_key": "second"}]}
        schema_path = SCHEMA_DIR / "02_references_schema.json"
        self.assertEqual([], validate_document(data, schema_path))
        data["references"][1]["citation_key"] = "first"
        errors = validate_document(data, schema_path)
        self.assertTrue(any("duplicate citation key" in e for e in errors))

    def test_reference_integrity_handles_invalid_types(self):
        for references in (None, 1, [None], [{"citation_key": []}]):
            with self.subTest(references=references):
                self.assertTrue(validate_document({"references": references}, SCHEMA_DIR / "02_references_schema.json"))

    def test_generated_tsv_matches_schemas_without_warnings(self):
        for path in sorted(SCHEMA_DIR.glob("[0-9]*_schema.json")):
            with self.subTest(schema=path.name):
                warnings = []
                schema = resolve_schema_refs(json.loads(path.read_text(encoding="utf-8")), SCHEMA_DIR)
                rows = extract_schema_metadata(schema, warnings.append)
                self.assertEqual([], warnings)
                output = io.StringIO(newline="")
                writer = csv.DictWriter(output, fieldnames=FIELDNAMES, delimiter="\t", lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
                destination = SCHEMA_DIR / "tsv_output" / (path.stem.replace("_schema", "") + ".tsv")
                self.assertEqual(output.getvalue(), destination.read_text(encoding="utf-8"))

    def test_tsv_displays_allowed_sample_contributor_roles(self):
        path = SCHEMA_DIR / "03_collection_schema.json"
        schema = resolve_schema_refs(json.loads(path.read_text(encoding="utf-8")), SCHEMA_DIR)
        rows = extract_schema_metadata(schema)
        role_rows = [r for r in rows if "preserver" in r["enum"].split(", ")]
        self.assertTrue(role_rows)
        self.assertTrue(any("collector" in r["enum"].split(", ") for r in role_rows))

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCHEMA_DIR / "validate_schemas.py"), *map(str, args)],
            capture_output=True, text=True, check=False,
        )

    def test_cli_accepts_valid_record_and_rejects_primitive_analysis_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            args = ("--schema", SCHEMA_DIR / "09_analysis_schema.json", "--data", path)
            path.write_text('{"analysis": [{"assembly_role": {"assembly": "primary"}}]}', encoding="utf-8")
            self.assertEqual(0, self.run_cli(*args).returncode)
            path.write_text('{"analysis": [null, 42, "not an analysis object"]}', encoding="utf-8")
            result = self.run_cli(*args)
            self.assertEqual(1, result.returncode)
            self.assertIn("/analysis/0", result.stderr)
            self.assertIn("/analysis/1", result.stderr)
            self.assertIn("/analysis/2", result.stderr)

    def test_cli_rejects_non_json_numbers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text('{"analysis": NaN}', encoding="utf-8")
            result = self.run_cli("--schema", SCHEMA_DIR / "09_analysis_schema.json", "--data", path)
            self.assertEqual(1, result.returncode)
            self.assertIn("not a JSON number", result.stderr)

    def test_cli_requires_schema_and_data_together(self):
        self.assertEqual(2, self.run_cli("--schema", SCHEMA_DIR / "09_analysis_schema.json").returncode)


if __name__ == "__main__":
    unittest.main()
