# Reviewer update log

This log records completed changes and their verification as we address the
[reviewer checklist](reviewer-checklist.md). Entries provide wording for the response to reviewers.
Changes recorded here refer to the local working tree until the revised submission is published.

## 2026-09-23: Reviewer C - Software citation

**Request:** Add `CITATION.cff` and cite the software repository in the bibliography.

**Changes:**

- Added [CITATION.cff](../../CITATION.cff) with the software title, authors, ORCIDs, repository URL,
  and MIT license. Author names and order follow the manuscript.
- Added the `gendertagger_software_2026` entry to
  [gendertagger.bib](gendertagger.bib), including the repository URL and access date.
- Replaced the repository-only footnote in the Data Availability statement with a bibliography
  citation in [article.tex](article.tex).

**Response to the reviewer:** We added a `CITATION.cff` file containing the software citation metadata
and included the gendertagger repository in the bibliography. The Data Availability statement now
cites that bibliography entry.

**Status:** Addressed in the local working tree; the checklist item is marked complete.

**Verification:**

- `CITATION.cff` passed validation against the official CFF 1.2.0 JSON Schema.
- A standalone citation using the manuscript's `eceasst.bst` compiled successfully and was visually
  checked. The entry renders as `[KNW26]` with the authors, title, repository URL, and access date.
- The locked documentation-policy check passed.

**Build note for the authors:** The full manuscript build stops at the existing DOI
`10.17175/WP_2026` with `Missing $ inserted`. The unchanged manuscript has the same error.
This separate bibliography-formatting issue was not altered as part of the software-citation item.

## 2026-09-23: Reviewer C and Reviewer I14 - GND and authority-source selection

**Requests:** Expand GND at its first occurrence (Reviewer C, page 6) and explain the choice of GND
and alternatives including Wikidata, VIAF, and Getty ULAN (Reviewer I14).

**Changes:**

- Expanded GND at its first occurrence in the Workflow Description in [article.tex](article.tex)
  and shortened the repeated expansion in the GND paragraph.
- Specified German-speaking digital scholarship in the GND paragraph's opening sentence.
- Added the domain and data rationale: predominantly German-language sources and existing editorial
  authority links that primarily use GND identifiers.
- Explained the exclusion of VIAF with reference to the interface reliability and governance concerns
  documented by Bargioni following the January 2025 redesign.
- Added direct lookup in Wikidata and Getty's Union List of Artist Names (ULAN) as possible future
  extensions.
- Added the `bargioni_viaf_2025` reference to [gendertagger.bib](gendertagger.bib) and cited it in the
  new rationale.

**Response to Reviewer C:** We expanded GND as the German Integrated Authority File
(*Gemeinsame Normdatei*) at its first occurrence in the Workflow Description, where its role in
identifying persons and retrieving authority records is described.

**Response to Reviewer I14:** We clarified that the choice of GND reflects the predominantly
German-language source material and the existing editorial GND links. We explained why VIAF was
excluded, citing Bargioni (2025) on interface reliability and governance concerns following its
January 2025 redesign. We also identified direct lookup in Wikidata and Getty ULAN as possible
future extensions.

**Status:** Addressed in the local working tree; both checklist items are marked complete.

**Verification:**

- Bibliographic metadata and the scope of the VIAF critique were checked against
  [Bargioni's journal article](https://doi.org/10.5860/ital.v44i4.17384).
- BibTeX processed the new reference successfully using the manuscript's `eceasst.bst` and generated
  the citation label `[Bar25]` with the correct DOI.
- The locked documentation-policy check passed.
- The full manuscript PDF was not rebuilt for this edit; the existing build blocker is recorded in
  the software-citation entry above.

## 2026-09-23: Reviewer C - Local authority snapshot maintenance

**Request:** Explain that local authority snapshots need updating to incorporate later changes
(annotated PDF, page 7).

**Changes:** Added three sentences to the GND paragraph in [article.tex](article.tex). They explain
that the local snapshot must be refreshed to include subsequent additions and corrections to the
GND, and describe the current backend's retention of immutable source dumps and derived lookups,
checksums, source and compiler provenance, and references from method executions to the exact lookup
used.

**Response to the reviewer:** We clarified the maintenance tradeoff of local authority snapshots:
subsequent additions and corrections require refreshing the snapshot. We also explained how the
current backend preserves traceability across updates by retaining source dumps and derived lookup
snapshots with checksums and compilation provenance, and recording the exact lookup used by each
method execution.

**Status:** Addressed in the local working tree; the checklist item is marked complete.

**Verification:** The description was checked against the implemented source/lookup registration
and execution provenance, with supporting tests inspected. The wording identifies this as
functionality of the current backend.
