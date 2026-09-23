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

## 2026-09-23: Reviewer C - Parenthetical-qualifier implementation

**Request:** Clarify whether the parenthetical-qualifier rule is implemented within gendertagger
or in separate code (annotated PDF, page 7).

**Changes:** Changed the opening of the parenthetical-qualifier paragraph in [article.tex](article.tex)
to state explicitly that the heuristic is implemented within gendertagger.

**Response to the reviewer:** We clarified that the parenthetical-qualifier heuristic is implemented
within gendertagger.

**Status:** Addressed in the local working tree; the checklist item is marked complete.

**Verification:** Confirmed the implementation in `ParentheticalQualifierMethod` and its integration
in the backend method registry by source inspection.

## 2026-09-23: Reviewer C - Resulting label terminology

**Request:** Clarify "combined label" and consider "resulting label" or "post-voting label"
(annotated PDF, page 10; two annotations).

**Changes:**

- Replaced all eight occurrences of "combined label" with "resulting label" in
  [article.tex](article.tex).
- Defined the term at first use as the automated output of aggregation, including any authority
  override, before human review.
- Renamed the corresponding row and two column headings to "Resulting label" and updated the
  distribution table's caption to match.

**Response to the reviewer:** We now use "resulting label" consistently and define it at first use
as the automated output of aggregation, including any authority override, before human review.
The corresponding table headings, row label, and caption have been updated. This terminology covers
both voting and authority overrides while distinguishing the automated result from later human
review decisions.

**Status:** Addressed in the local working tree; the checklist item is marked complete. This is a
terminology clarification in the manuscript; no code change is required.

## 2026-09-23: Reviewer I1 - Abstract structure and corpus size

**Request:** Consolidate the abstract paragraphs, explain what `N = 8,277` counts, and consider
whether the number belongs in the abstract.

**Changes:** Merged the three abstract paragraphs into one in [article.tex](article.tex). Replaced
`N = 8,277` with "comprising 8,277 entries" in the case-study sentence.

**Response to the reviewer:** We consolidated the abstract into a single paragraph and clarified
that 8,277 is the number of entries in the case-study person register. We retained the count to
indicate the scale of the study.

**Status:** Addressed in the local working tree; the checklist item is marked complete.

## 2026-09-23: Reviewer I2 - Authority files, GND scope, and gender metadata

**Request:** Explain "authority files," name GND where appropriate, consider the broader term
"terminologies," and clarify the scope.

**Changes:**

- Defined authority files as resources providing identifiers and descriptive records for persons
  and other entities in the opening Introduction paragraph of [article.tex](article.tex).
- Named and expanded GND in the study-scope sentence and shortened its later mention in the
  Workflow Description.
- Replaced the claim about missing person records with an explanation that gender information is
  optional in GND person records, so identifying a person does not necessarily provide gender data.
- Added the official GND field documentation to [gendertagger.bib](gendertagger.bib) as
  `sta_gnd_gender_2026` and cited it for the optional field.
- Retained the separate statement about male-centered and binary assumptions in GND subject
  terminology, supported by Aleksander (2025).

**Response to the reviewer:** We defined authority files and identified GND as the authority source
used in this study. We retained the more specific term "authority files" because the method
retrieves records about identified entities; "terminologies" would describe a broader range of
resources. The methods section explains the choice of GND and discusses VIAF, Wikidata, and Getty
ULAN. We also clarified that existing GND person records may lack gender information, citing the
official documentation of the optional field. The Aleksander citation now supports the distinct
statement about gender bias in subject terminology.

**Status:** Addressed in the local working tree; the checklist item is marked complete.

**Verification:**

- The optional-field claim and documentation metadata were checked against the official
  [GND field documentation](https://sta.dnb.de/wiki/Property:P300).
- The terminology-bias statement matches the scope of
  [Aleksander's published abstract](https://www.bibliothekskongress.at/abstracts/#240).
- BibTeX processed the documentation reference successfully with `eceasst.bst`; its generated
  entry contains the institution, version, update status, access date, and field-documentation URL.
- The locked documentation-policy check passed.

## 2026-09-23: Reviewer I3 - Footnote pagination

**Request:** Prevent footnote 1 from splitting across pages.

**Changes:** Added `\interfootnotelinepenalty=10000` to the preamble of
[article.tex](article.tex), preventing footnotes from splitting across pages. Footnote wording is
unchanged.

**Response to the reviewer:** We adjusted the LaTeX footnote setting to prevent splitting across
pages and verified that footnote 1, including its complete URL, appears on a single page in the
revised rendering.

**Status:** Addressed in the local working tree; the checklist item is marked complete.

**Verification:** A fresh temporary rendering was inspected visually on pages 1 and 2. The marker
and complete text of footnote 1 appear on page 2. The setting also protects against splitting as
subsequent text edits change pagination.

**Build note for the authors:** The rendering was generated, but the complete build still reports
the existing `Missing $ inserted` error for DOI `10.17175/WP_2026`. This unrelated bibliography
issue was not changed. The temporary verification PDF did not replace the manuscript PDF in the
working tree.

## 2026-09-23: Reviewer I4 - TEI website footnote

**Request:** Add a link to TEI in a footnote at its explanation in the Introduction.

**Changes:** Added a footnote after the sentence explaining TEI in [article.tex](article.tex),
linking to `https://tei-c.org/` and giving the access date as 23 September 2026.

**Response to the reviewer:** We added a footnote linking to the official Text Encoding Initiative
website at the introductory explanation of TEI, including an access date.

**Status:** Addressed in the local working tree; the checklist item is marked complete.

**Verification:** The [official TEI website](https://tei-c.org/) was checked before adding the link.
