# GenomeNote Project JSON schemas

This fork contains validation repairs to the proposed GenomeNote data schemas,
based on upstream commit `c4f67db8e92e69845bc0f400ca130d55ea12e81d`.
These are fork changes for review, not a new upstream release or an agreed portal
submission format. See [the correction notes](SCHEMA_CORRECTIONS.md) for the data
shapes and compatibility decisions.

The ten numbered schemas describe component records. `_author_schema.json` and
`_protocol_schema.json` contain shared definitions. The set does not yet define a
single combined genome-note document or a complete article-rendering contract.

## Validate schemas and records

Use Python 3.10 or later in a virtual environment:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python validate_schemas.py
.venv/bin/python -m unittest discover -s tests -v
```

To validate a component record, including its local shared references:

```sh
.venv/bin/python validate_schemas.py \
  --schema 09_analysis_schema.json --data /path/to/analysis.json
```

This command first checks the schemas against JSON Schema Draft 2020-12, then
applies repository lint rules for misplaced fields and keywords that cannot
apply to the declared type. It resolves schema references locally and does not
download schemas. Record validation enables `format` checks and also checks
reference citation keys for duplicates. Standard JSON Schema validation alone
does not check citation-key uniqueness.

`help`, `source` and `recommended` are project annotations, not validation rules.
The lint allows these explicitly. Other extension keywords need an intentional
change to the lint policy; JSON Schema itself permits extension keywords.

## Readable field tables

The TSV files are generated documentation, not validation schemas. Regenerate
them after changing a schema:

```sh
.venv/bin/python json_to_tsv_converter.py
```

Tests verify that the TSVs match the schemas and that generation produces no
warnings. GitHub Actions runs the same checks.

## Scope and remaining decisions

The repairs make the existing field rules effective. They do not establish
publication completeness: many sections remain optional, extra data properties
remain allowed, and an empty object can pass a component schema. The intentionally
open `publication_metadata.ebp_analysis_metrics` array still has no item schema.
Required sections, cross-record links, units, missing-value policy, authorship
rules, template profiles and whole-article rendering still need agreement.

Contributors can now have a `preserver` role. The existing `curator` author role
and curation contributors remain available. Representing a contributor does not
by itself decide whether they must be included as a manuscript author.

## Sample, extraction, library and sequencing links

Schemas 04–06 now provide optional explicit links: `extraction_id`,
`library_id` and `source_extraction_ids`. A BioSample accession or sample role
does not identify an individual extraction. See the
[synthetic linked example](examples/provenance/README.md) for the data and command
to check these relationships across component files. The separate
`validate_provenance.py` command checks identifiers and references that ordinary
JSON Schema validation cannot check across these files.

These are additive proposals in this fork. Existing unlinked records still pass
the component schemas; use `--require-complete` with the provenance command to
reject missing extraction-to-library-to-run links. Additional relationships,
laboratory measurement stages and broader publication rules remain to be defined.
