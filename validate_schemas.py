#!/usr/bin/env python3
"""Check this schema set, or validate a record using local references only."""

import argparse
import json
from pathlib import Path
from urllib.parse import urljoin

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

SCHEMA_DIR = Path(__file__).resolve().parent
MAP_SCHEMAS = {"properties", "patternProperties", "$defs", "dependentSchemas"}
LIST_SCHEMAS = {"allOf", "anyOf", "oneOf", "prefixItems"}
SINGLE_SCHEMAS = {
    "items", "contains", "additionalProperties", "unevaluatedProperties",
    "unevaluatedItems", "propertyNames", "not", "if", "then", "else", "contentSchema",
}
# This is a repository lint policy, not a claim that extension keywords are
# forbidden by JSON Schema. Add intentional extensions here and document them.
KEYWORDS = MAP_SCHEMAS | LIST_SCHEMAS | SINGLE_SCHEMAS | {
    "$schema", "$id", "$ref", "$anchor", "$dynamicRef", "$dynamicAnchor",
    "$vocabulary", "$comment", "type", "enum", "const", "multipleOf",
    "maximum", "exclusiveMaximum", "minimum", "exclusiveMinimum",
    "maxLength", "minLength", "pattern", "maxItems", "minItems", "uniqueItems",
    "maxContains", "minContains", "maxProperties", "minProperties", "required",
    "dependentRequired", "format", "contentEncoding", "contentMediaType",
    "title", "description", "default", "deprecated", "readOnly", "writeOnly",
    "examples", "source", "help", "recommended",
}
OBJECT_KEYWORDS = {
    "properties", "patternProperties", "additionalProperties", "required",
    "dependentRequired", "dependentSchemas", "propertyNames", "minProperties",
    "maxProperties", "unevaluatedProperties",
}
ARRAY_KEYWORDS = {
    "items", "prefixItems", "contains", "minContains", "maxContains", "minItems",
    "maxItems", "uniqueItems", "unevaluatedItems",
}


def read_json(path):
    def reject_constant(value):
        raise ValueError(f"{path}: {value} is not a JSON number")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject_constant)


def pointer(parts):
    return "/" + "/".join(str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def schema_nodes(schema, path=(), base_uri=""):
    """Visit schema positions, never example/default/const instance data."""
    if not isinstance(schema, dict):
        return
    base_uri = urljoin(base_uri, schema.get("$id", ""))
    yield path, schema, base_uri
    for key, value in schema.items():
        if key in MAP_SCHEMAS and isinstance(value, dict):
            for name, child in value.items():
                yield from schema_nodes(child, path + (key, name), base_uri)
        elif key in LIST_SCHEMAS and isinstance(value, list):
            for index, child in enumerate(value):
                yield from schema_nodes(child, path + (key, index), base_uri)
        elif key in SINGLE_SCHEMAS:
            yield from schema_nodes(value, path + (key,), base_uri)


def lint_schema(schema):
    """Catch misplaced definitions that standard meta-validation may accept."""
    errors = []
    for path, node, _ in schema_nodes(schema):
        for key in sorted(node.keys() - KEYWORDS):
            errors.append(f"{pointer(path + (key,))}: unknown keyword or misplaced field")
        declared = node.get("type")
        types = set(declared) if isinstance(declared, list) else {declared}
        for instance_type, keywords in (("object", OBJECT_KEYWORDS), ("array", ARRAY_KEYWORDS)):
            if declared is not None and instance_type not in types:
                for key in sorted(node.keys() & keywords):
                    errors.append(
                        f"{pointer(path + (key,))}: applies to {instance_type}s, "
                        f"but this schema declares {declared!r}"
                    )
    return errors


def load_schema_set(directory):
    schemas = {}
    resources = []
    for path in sorted(Path(directory).glob("*_schema.json")):
        path = path.resolve()
        schema = read_json(path)
        # Give relative file references a base without changing the source files.
        if isinstance(schema, dict):
            schema = {"$id": path.as_uri(), **schema}
        schemas[path] = schema
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError:
            # check_schemas reports the meta-schema errors. Invalid metadata
            # must not reach Resource/Registry construction first.
            continue
        resource = Resource.from_contents(schema, default_specification=DRAFT202012)
        resources.append((path.as_uri(), resource))
        if isinstance(schema, dict) and schema.get("$id") != path.as_uri():
            resources.append((schema["$id"], resource))
    # The default registry does not retrieve missing remote resources.
    return schemas, Registry().with_resources(resources)


def check_schemas(directory=SCHEMA_DIR):
    schemas, registry = load_schema_set(directory)
    errors = []
    if not schemas:
        return [f"{directory}: no *_schema.json files found"]
    for path, schema in schemas.items():
        meta_errors = list(Draft202012Validator(Draft202012Validator.META_SCHEMA).iter_errors(schema))
        errors.extend(f"{path.name}{pointer(e.absolute_path)}: {e.message}" for e in meta_errors)
        if meta_errors:
            continue
        errors.extend(f"{path.name}{e}" for e in lint_schema(schema))
        for node_path, node, base_uri in schema_nodes(schema, base_uri=path.as_uri()):
            for keyword in ("$ref", "$dynamicRef"):
                if keyword in node:
                    try:
                        registry.resolver(base_uri).lookup(node[keyword])
                    except Unresolvable as error:
                        errors.append(f"{path.name}{pointer(node_path)}: unresolved {keyword}: {error}")
    return errors


def load_validator(schema_path):
    schema_path = Path(schema_path).resolve()
    schemas, registry = load_schema_set(schema_path.parent)
    schema = schemas[schema_path]
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def validate_document(data, schema_path):
    validator = load_validator(schema_path)
    errors = [f"{pointer(e.absolute_path)}: {e.message}" for e in validator.iter_errors(data)]
    # Standard JSON Schema cannot enforce uniqueness of one property across
    # records. Citation keys identify references; titles do not.
    if isinstance(data, dict) and "references" in validator.schema.get("properties", {}):
        seen = set()
        references = data.get("references", [])
        for index, reference in enumerate(references if isinstance(references, list) else []):
            key = reference.get("citation_key") if isinstance(reference, dict) else None
            if isinstance(key, str):
                if key in seen:
                    errors.append(f"/references/{index}/citation_key: duplicate citation key {key!r}")
                seen.add(key)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path, help="Component schema for the data record")
    parser.add_argument("--data", type=Path, help="JSON data record to validate")
    args = parser.parse_args()
    if (args.schema is None) != (args.data is None):
        parser.error("--schema and --data must be supplied together")
    if args.schema and (args.schema.name.startswith("_") or not args.schema.name.endswith("_schema.json")):
        parser.error("Choose a numbered component schema; shared definitions are not record schemas")
    try:
        directory = args.schema.resolve().parent if args.schema else SCHEMA_DIR
        errors = check_schemas(directory)
        if not errors and args.data:
            errors = validate_document(read_json(args.data), args.schema)
    except (OSError, ValueError, KeyError, Unresolvable) as error:
        parser.exit(1, f"Validation could not run: {error}\n")
    if errors:
        parser.exit(1, "\n".join(errors) + "\n")
    if args.data:
        print(f"Valid: {args.data} against {args.schema.name} (including configured format and integrity checks)")
    else:
        print(f"Checked {len(list(directory.glob('*_schema.json')))} schemas: Draft 2020-12, structural lint and local references passed")


if __name__ == "__main__":
    main()
