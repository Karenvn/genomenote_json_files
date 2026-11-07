# Schema correction notes

These changes are based on upstream
[`c4f67db8`](https://github.com/sanger-tol/genomenote_json_files/commit/c4f67db8e92e69845bc0f400ca130d55ea12e81d).
They preserve the proposed fields and existing value constraints where possible.
Where the original structure was ambiguous, the interpretation used here is
listed below for review. This fork does not establish portal acceptance.

## Structural repairs

- Replaced shorthand property definitions such as `"journal_name": "string"`
  with JSON Schema objects such as `"journal_name": {"type": "string"}`.
- Added `items` schemas to arrays whose record fields were placed under
  `properties` on the array itself. The affected arrays include journal data,
  assembly statistics and subrecords, analysis records and annotation results.
- Moved intended field definitions inside the relevant object `properties`
  blocks, so the existing type, range and required-field checks take effect.

The following are paths in **data records**, using `[]` for array entries:

| Schema | Corrected data path and interpretation |
| --- | --- |
| 01 | `publication_metadata.journal_data[]` contains journal record objects. `publication_metadata.genome_note_data` is an object. |
| 06 | `methods.sample_processing[].raw_data[]` and `methods.sample_processing[].cumulative_raw_data_statistics` belong to each sample-role group, alongside `sample_role` and `library_sequencing`. Totals here are per group. |
| 07 | `assembly_stats[]` contains sibling `assembly_information` and `assembly_analysis` objects. |
| 07 | `assembly_stats[].assembly_information.organelles[]` records the organelles for that assembly. |
| 07 | `assembly_stats[].assembly_analysis.ploidy` is an object; `kmer_analysis[]` and `raw_data_object[]` contain objects. Organelle-method comparators also contain objects. |
| 09 | `analysis[]` contains objects. `analysis[].assembly_role` retains its existing object shape, for example `{"assembly": "primary"}`. |
| 09 | `analysis[].GAP_analysis_data` is an object containing the eight analysis components. `sequence_composition[]`, `merqury[]` and `busco[]` remain arrays; the other components remain objects. |
| 10 | `annotation[]`, its `data_used[]`, and BUSCO `results[]` contain objects. BUSCO `lineages` and OMARK `clades` retain their existing object shapes. |

In schema 09, the misspelled `worfklow` field is now `workflow`, a string. For
array components it belongs to each result object; for object components it is
a property of that component. Its value is still an identifier; a cross-reference
target and referential-integrity rule have not been established.

The existing assembly-statistics requirements and BUSCO result `mode`
requirement now apply to the intended objects. No new mandatory sections or
minimum array sizes were introduced. Data that previously passed because its
fields were not inspected may now fail validation.

## Contributor and extraction fixes

- Schema 03 accepts `preserver` alongside `collector` and `identifier` in
  sample contributor roles. The shared author schema also accepts `preserver`.
- The shared author GAL conditional now tests `collection`, which is the
  existing author-role value. Previously it tested `collector`, which that
  enum did not permit. Sample-contributor roles still use `collector`; these
  two existing vocabularies have not been merged.
- Schema 04 accepts `ont` in its inner extraction sample-role list, consistent
  with the existing outer list.

These changes allow contributions to be represented. They do not automate
authorship decisions or remove existing author-data requirements. In particular,
sample contributors still require an AuthorsDB identifier under schema 03;
handling contributors absent from that database needs a separate decision.

## Reference fixes

Schema 02 required three fields it did not define: `publication_type`,
`accession` and `accession_type`. These obsolete requirements were removed.
`title`, `citation_key`, `authors` and `entry_type` remain required. Bibliographic
identifiers use the existing optional `identifier` object; dataset entries
still require their existing `data_accession` object. No identifier is invented
for records that do not have one.

The ISBN placeholder was replaced with basic ISBN-10/ISBN-13 format checking.
It permits a final X/x for ISBN-10, requires a 978/979 prefix for ISBN-13, and
allows single space or hyphen separators. It does not validate checksums or
registered hyphenation groups.

The nonstandard `uniqueItemProperties` keyword was removed. The supplied
validator checks that reference `citation_key` values are unique. Repeated
titles are allowed because different references can share a title. Applications
using another validator must implement citation-key uniqueness separately.

## What validation does not settle

- These are ten component schemas, not a defined combined document envelope.
  A producer must select the appropriate schema for each exported component.
- Optional fields may be omitted. A missing measurement must not be replaced
  with zero to satisfy a numeric type. The existing numeric type constraints
  reject `null`; open properties and unconstrained items may still accept it.
  An agreed missing-value policy is still needed.
- Unknown data properties remain allowed. A passing result does not mean every
  supplied field was checked, or that the document is publication-ready.
- Schema 07 retains the existing `genome_size` name and its help text meaning
  assembly length in base pairs. The distinction from estimated genome size
  should be agreed before an exporter maps these values.
- Cross-component sample/assembly/workflow/reference links are not yet checked.
  This repair does not add scientific consistency checks or publication rules.
- Template versions, programme profiles, optional introductions, edited prose,
  author ordering and complete article/PDF export are separate workflow work.

The test suite includes positive records, malformed records that previously
escaped validation, local reference resolution, repository lint checks and TSV
consistency. It uses synthetic records and does not publish manuscript data.
The TSV converter also shows allowed values for scalar array entries, including
contributor roles, on their array's row.
