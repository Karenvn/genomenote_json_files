# Synthetic extraction-to-run example

These invented records demonstrate two extractions from the **same BioSample**:

| Sample | Extraction | Library | Archive run |
| --- | --- | --- | --- |
| sample-A | extract-A | library-A | run-1 |
| sample-A | extract-B | library-B | run-2 |
| sample-A | extract-A and extract-B | library-pool | run-3 |

The third row illustrates a library prepared from pooled extraction inputs.
It is not evidence that pooling occurred in any actual genome note. Identifiers,
methods, instrument and counts are synthetic, not real archive accessions.

Run this from the repository root:

```sh
python validate_provenance.py \
  --collection examples/provenance/sample.json \
  --extractions examples/provenance/extractions.json \
  --libraries examples/provenance/libraries.json \
  --sequencing examples/provenance/sequencing.json \
  --require-complete
```

The validator checks each component against its schema, then checks the supplied
links. It detects duplicate extraction/library identifiers, unresolved links,
conflicting run-to-library, run-to-experiment or run-to-sample assignments,
repeated runs within one sequencing view, and contradictory
experiment-to-library associations. Several experiments
may use the same physical library. The same run may appear once in each of
`library_sequencing` and `raw_data`, provided the links agree.

New fields remain optional in the component schemas so existing data are not
rejected merely for lacking them. Without `--require-complete`, missing links
produce warnings; supplied broken links still fail. With that option, missing
identifiers and links fail too. It does not establish scientific completeness or
prove that the declared laboratory relationships are correct.

The optional `--collection` argument accepts one or more schema 03 files, one
per BioSample, to check `sample_accession` links. Without it, sample links are
explicitly reported as unchecked. The checker does not infer whether a tissue,
source-individual or pooled BioSample should be substituted for another.

These separate files exercise the existing component schemas. They do not
define a new combined article/data envelope or implement a builder exporter.
