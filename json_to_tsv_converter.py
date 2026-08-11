#!/usr/bin/env python3
"""
Convert JSON schema files to organized TSV files.
This script processes genomic JSON schema files and outputs them as TSV files
with a flattened, readable structure. Handles conditional if/then/else schemas
and $ref references to external schemas.
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List


def resolve_schema_refs(schema: Dict[str, Any], schema_dir: Path, loaded_schemas: Dict = None) -> Dict[str, Any]:
    """
    Recursively resolve all $ref references in a schema.

    Args:
        schema: The schema object to resolve
        schema_dir: Directory containing schema files
        loaded_schemas: Cache of already-loaded schemas

    Returns:
        The schema with all $refs resolved
    """
    if loaded_schemas is None:
        loaded_schemas = {}

    def resolve_value(value: Any) -> Any:
        """Recursively resolve $ref in a value."""
        if isinstance(value, dict):
            if "$ref" in value:
                ref = value["$ref"]
                # Parse reference: "author_schema.json#/$defs/author"
                if "#" in ref:
                    file_ref, json_ptr = ref.split("#", 1)
                else:
                    file_ref = ref
                    json_ptr = ""

                # Load referenced file if not cached
                ref_path = schema_dir / file_ref
                if str(ref_path) not in loaded_schemas:
                    try:
                        with open(ref_path, "r", encoding="utf-8") as f:
                            loaded_schemas[str(ref_path)] = json.load(f)
                    except FileNotFoundError:
                        print(f"Warning: Could not find referenced schema {ref_path}")
                        return value

                ref_schema = loaded_schemas[str(ref_path)]

                # Navigate JSON pointer
                if json_ptr:
                    parts = json_ptr.strip("/").split("/")
                    for part in parts:
                        if isinstance(ref_schema, dict) and part in ref_schema:
                            ref_schema = ref_schema[part]
                        else:
                            print(f"Warning: Invalid JSON pointer path {json_ptr}")
                            return value

                # Return resolved schema (recursive in case it has more $refs)
                return resolve_value(ref_schema.copy() if isinstance(ref_schema, dict) else ref_schema)

            # Recursively resolve all dict values
            return {k: resolve_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [resolve_value(item) for item in value]
        else:
            return value

    return resolve_value(schema)


def extract_schema_metadata(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract property metadata from a JSON schema, flattening all properties.
    Handles if/then/else conditional schemas.

    Args:
        schema: The JSON schema object

    Returns:
        A list of dictionaries containing all properties with parent relationships
    """
    rows = []

    properties = schema.get("properties", {})

    def process_property(prop_name: str, prop_schema: Any, parent_name: str = "") -> None:
        """Recursively process properties and add rows."""
        if not isinstance(prop_schema, dict):
            return

        # Get basic info about this property
        prop_type = prop_schema.get("type", "")
        description = prop_schema.get("help", "")
        pattern = prop_schema.get("pattern", "")
        required = prop_schema.get("required", False)

        # Create row for this property
        row = {
            "property_name": prop_name,
            "parent_property": parent_name,
            "type": prop_type,
            "description": description,
            "pattern": pattern,
            "required": "Yes" if required else "No",
        }
        rows.append(row)

        # If this property has nested properties, process them
        if "properties" in prop_schema and isinstance(prop_schema["properties"], dict):
            nested_props = prop_schema["properties"]
            for nested_name, nested_schema in nested_props.items():
                process_property(nested_name, nested_schema, prop_name)

        # If this is an array with items, process the item schema
        if prop_type == "array" and "items" in prop_schema:
            items_schema = prop_schema["items"]
            if isinstance(items_schema, dict):
                if "properties" in items_schema and isinstance(items_schema["properties"], dict):
                    for item_prop_name, item_prop_schema in items_schema["properties"].items():
                        process_property(item_prop_name, item_prop_schema, prop_name)

                # Handle if/then/else conditional schemas
                if "if" in items_schema and ("then" in items_schema or "else" in items_schema):
                    # Process "then" branch properties
                    if "then" in items_schema and isinstance(items_schema["then"], dict):
                        then_schema = items_schema["then"]
                        if "properties" in then_schema and isinstance(then_schema["properties"], dict):
                            then_props = then_schema["properties"]
                            for then_prop_name, then_prop_schema in then_props.items():
                                # Check if this property was already processed
                                already_processed = any(
                                    r["property_name"] == then_prop_name and r["parent_property"] == prop_name
                                    for r in rows
                                )
                                if not already_processed:
                                    process_property(then_prop_name, then_prop_schema, prop_name)

                    # Process "else" branch properties
                    if "else" in items_schema and isinstance(items_schema["else"], dict):
                        else_schema = items_schema["else"]
                        if "properties" in else_schema and isinstance(else_schema["properties"], dict):
                            else_props = else_schema["properties"]
                            for else_prop_name, else_prop_schema in else_props.items():
                                # Check if this property was already processed
                                already_processed = any(
                                    r["property_name"] == else_prop_name and r["parent_property"] == prop_name
                                    for r in rows
                                )
                                if not already_processed:
                                    process_property(else_prop_name, else_prop_schema, prop_name)

    # Process all top-level properties
    for prop_name, prop_schema in properties.items():
        process_property(prop_name, prop_schema)

    return rows


def write_tsv_file(filepath: Path, rows: List[Dict[str, Any]]) -> None:
    """
    Write rows to a TSV file.

    Args:
        filepath: The output file path
        rows: The data rows to write
    """
    if not rows:
        return

    # Get all unique keys across all rows, in order
    fieldnames = [
        "property_name",
        "parent_property",
        "type",
        "description",
        "pattern",
        "required",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def process_json_files(input_dir: Path, output_dir: Path) -> None:
    """
    Process all JSON files in input directory and convert to TSV.

    Args:
        input_dir: Directory containing JSON files
        output_dir: Directory to write TSV files
    """
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process each JSON file
    json_files = sorted(input_dir.glob("*_schema.json"))

    if not json_files:
        print(f"No JSON schema files found in {input_dir}")
        return

    print(f"Found {len(json_files)} JSON files to process\n")

    for json_file in json_files:
        print(f"Processing: {json_file.name}")

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                schema = json.load(f)

            # Resolve all $ref references
            schema = resolve_schema_refs(schema, input_dir)

            # Extract metadata
            rows = extract_schema_metadata(schema)

            # Create output filename
            output_filename = json_file.stem.replace("_schema", "") + ".tsv"
            output_path = output_dir / output_filename

            # Write TSV file
            write_tsv_file(output_path, rows)

            print(f"  ✓ Written to: {output_path.name} ({len(rows)} rows)")

        except json.JSONDecodeError as e:
            print(f"  ✗ Error decoding JSON: {e}")
        except Exception as e:
            print(f"  ✗ Error processing file: {e}")

    print(f"\nConversion complete! TSV files written to: {output_dir}")


def main():
    """Main entry point."""
    # Use the current directory if no arguments provided
    script_dir = Path(__file__).parent
    input_dir = script_dir
    output_dir = script_dir / "tsv_output"

    print("=" * 60)
    print("JSON to TSV Converter for Genome Note Schemas")
    print("=" * 60)
    print()

    process_json_files(input_dir, output_dir)


if __name__ == "__main__":
    main()
