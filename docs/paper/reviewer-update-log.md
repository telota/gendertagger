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

## 2026-09-23: Reviewer I5 - Authority lookup explanation

**Request:** Explain what "authority data queries" means in the Introduction.

**Changes:** Replaced the phrase in [article.tex](article.tex) with "retrieval of recorded gender
information from a local GND snapshot using the register's GND identifiers."

**Response to the reviewer:** We replaced the general phrase with an explicit description of the
lookup, identifying the information retrieved, the local GND snapshot as its source, and the
register's GND identifiers as the basis for matching records.

**Status:** Addressed in the local working tree; the checklist item is marked complete.

## 2026-09-23: Reviewer I6 - Transformer capitalization

**Request:** Check whether "Transformer" should be lowercase in running text.

**Changes:** Changed four occurrences of "Transformer-based" to "transformer-based" in
[article.tex](article.tex): the abstract, Introduction, methods overview, and Conclusion. Retained
"Transformer-Based Name Classifiers" as a heading, consistent with the paper's heading style.

**Response to the reviewer:** We standardized "transformer-based" to lowercase throughout the
running text, while retaining capitalization in the section heading.

**Status:** Addressed in the local working tree; the checklist item is marked complete.

## 2026-09-23: Reviewer I8 - Study Design opening paragraph

**Request:** Consolidate submitted manuscript lines 91-97 into a single paragraph.

**Changes:** Removed the paragraph break between the two opening passages under Study Design in
[article.tex](article.tex). Their wording and the existing footnote are unchanged.

**Response to the reviewer:** We consolidated the opening passages of the Study Design section
into one paragraph.

**Status:** Addressed in the local working tree; the checklist item is marked complete.

## 2026-09-23: Reviewer I9 - Descriptive constraint headings

**Request:** Replace "First... Second..." with descriptive LaTeX paragraph headings.

**Changes:** Replaced the five ordinal openings in [article.tex](article.tex) with
`\paragraph{...}` headings: "Heterogeneous Register Entries," "Classifier Coverage and Output
Normalization," "Limits of Manual Review," "Provenance and Interpretive Responsibility," and
"Organizations in the Person Register." Capitalized the following word in each paragraph; the
remaining paragraph text is unchanged.

**Response to the reviewer:** We replaced the ordinal openings with descriptive paragraph headings
that identify each of the five design constraints.

**Status:** Addressed in the local working tree; the checklist item is marked complete.

## 2026-09-23: Reviewer I10 and I17-I22 - English translations

**Request:** Translate the German output label and examples identified in the running text and
Table 6.

**Changes:** Added English glosses in square brackets in [article.tex](article.tex), retaining the
original German label and source phrases:

- Translated `uneindeutig` as "ambiguous."
- Translated the daughter, wife, sister, mother, and husband expressions, including the named
  examples and their repeated occurrences in the methods description and tables.
- Translated the adjacent `Sohn der ...` example as "son of ..." for consistency.
- Added "Baroness von Canitz," "physician in Berlin," and "residing at Friedrichsgracht 50" to
  Table 6, together with glosses for its standalone `Baronin`, `Arzt`, and `Frau des` expressions.

**Response to the reviewer:** We added English translations alongside the German label and
examples at all identified locations, including repeated examples in the tables. The German
originals remain visible because their wording and grammatical forms are relevant to the methods.

**Status:** I10 and I17-I22 are addressed in the local working tree and marked complete. The
separate final translation check was completed subsequently, as recorded below.

**Verification:** Documentation and whitespace checks passed. A source comparison confirmed that
all 22 glosses preserve the German originals and introduce no other manuscript changes. The seven
affected pages of a temporary PDF were inspected visually, including Tables 6 and 7; the added
glosses remain readable without clipping or overlap.

**Build note for the authors:** The temporary rendering was generated, but the complete build
still reports the existing `Missing $ inserted` error for DOI `10.17175/WP_2026`. The manuscript
PDF and build outputs in the working tree were not replaced.

## 2026-09-23: Final translation check - Remaining German examples

**Request:** Check all German examples and tables for English translations, including phrases
beyond the explicitly identified reviewer locations.

**Changes:** Reviewed the running text, TEI example, all seven tables, and both figures in
[article.tex](article.tex). Added English glosses for the remaining examples:

- Translated `Lehrerin in Gnadenfrei` and `Lehrerin` in the explanation following the TEI snippet,
  preserving the XML example.
- Glossed `Fournier, L. und Compagnie` in Table 6.
- Translated the painter descriptions in the error discussion and Table 7, explicitly identifying
  masculine and feminine forms where the distinction explains the classification error.
- Translated `Prediger in Halle`, `Prediger in`, and `Predigerin`, and explained how the missing word
  boundary creates the apparent feminine occupational noun.
- Added the intended English reading of `französisch-reformierterPredigerinHalle` in Table 7,
  preserving the malformed German string as evidence of the source error.

**Response to the reviewer:** We checked the remaining German examples throughout the manuscript
and added English translations alongside the originals. For examples involving grammatical gender
or missing spaces, the translations make the relevant linguistic distinction explicit. The TEI
example is translated in its accompanying explanation.

**Status:** Addressed in the local working tree; the final translation checklist item is marked
complete.

**Verification:** Documentation and whitespace checks passed. A source comparison confirmed that
the changes match the approved translation batch and preserve the German originals and verbatim
XML. The affected pages of a temporary PDF, including the TEI explanation and Tables 6 and 7, were
inspected visually; the translations remain readable without clipping or overlap.

**Build note for the authors:** The temporary rendering now has 23 pages. The build still reports
the existing `Missing $ inserted` error for DOI `10.17175/WP_2026`. The manuscript PDF and build
outputs in the working tree were not replaced.

## 2026-09-23: Reviewer I11, I15, I24, and I27 - Access dates and software citations

**Request:** Add access dates to the specified footnotes and consider bibliography entries for
software visibility. Footnote numbers below refer to the submitted manuscript.

**Changes:** Updated [article.tex](article.tex):

- I11: Added "Accessed 23 September 2026" to the person-register link (original footnote 2).
- I15: Added the same access date to the Hugging Face homepage and `Dannel/gender-name` dataset
  links (original footnotes 5 and 6).
- I24: Replaced both repository footnotes in Reproducibility and the Conclusion (original
  footnotes 9 and 10) with citations to the existing `gendertagger_software_2026` bibliography entry.
- I27: Added the same access date to the Gender & Data, KI Lab, and edition-editor links (original
  footnotes 11-13). Original footnote 14 had already been replaced by the software citation in
  Data Availability; its bibliography entry includes the access date.

**Response to the reviewer:** We added access dates to the specified web links and replaced the
repeated software repository footnotes with formal bibliography citations. The software reference
includes its access date, providing consistent attribution and visibility across the manuscript.

**Status:** I11, I15, I24, and I27 are addressed in the local working tree and marked complete.
The other undated links in original footnotes 1, 3, and 7 are outside this batch.

**Verification:** The linked resources were checked on 23 September 2026. The existing software
bibliography entry renders "Accessed 23 September 2026" through its `note` field; no bibliography
change was needed.

## 2026-09-23: Reviewer I28 - DOI and URL duplication

**Request:** Use either a DOI or a URL in each reference, avoiding duplicate links.

**Changes:** Removed the redundant `url` field from eight cited entries in
[gendertagger.bib](gendertagger.bib), retaining their DOIs: Bérubé's preprint, Beshero-Bondar,
Van Buskirk, Karimi, Lang, Liebing, padmajabfrl, and Santamaría. Escaped the underscore in Lang's
DOI as `10.17175/WP\_2026` so the existing LaTeX template can typeset it correctly. References
with only a URL retain it; other bibliography metadata is unchanged.

**Response to the reviewer:** We removed the duplicate web links from all eight affected
references, retaining their DOIs. URL-only references retain their web links.

**Status:** Addressed in the local working tree; I28 is marked complete.

**Verification:** A full temporary build completed successfully: all three LaTeX passes and the
BibTeX pass returned exit code 0. None of the 22 rendered references contains both a DOI and a
URL, and all eight changed entries retain their DOI. The bibliography pages were inspected
visually. Lang's PDF hyperlink resolves to `http://dx.doi.org/10.17175/WP_2026`, with the underscore
preserved and no backslash in the target. Documentation and whitespace checks passed.

**Build note for the authors:** This resolves the DOI-related build error recorded in earlier
entries. The temporary PDF has 22 pages. The manuscript PDF and build outputs in the working tree
were not replaced.

## 2026-09-23: Reviewer I16 - Internal reference in a footnote

**Request:** Move the inline link at submitted manuscript line 306 into a footnote.

**Changes:** Moved the reference to the TEI example from the running text of the locally hosted LLM
paragraph in [article.tex](article.tex) into a footnote: "See the example person entry in
Section~\ref{sec:tei-encoding}." The parenthetical examples and model citation are unchanged.

**Response to the reviewer:** We moved the internal cross-reference to the TEI example into a
footnote and shortened the surrounding sentence accordingly.

**Status:** Addressed in the local working tree; I16 is marked complete.

## 2026-09-23: Reviewer I7 - Case-study selection

**Request:** Explain why Schleiermacher digital was selected as the case study and what makes it
particularly suitable.

**Changes:** Added the approved selection rationale to the Introduction in
[article.tex](article.tex), immediately before the existing contributions list. It connects the
manageable corpus and its temporal and regional focus to planned work on other Academy editions,
identifies the enrichment challenges that make it useful for assessing complementary methods,
and explains the practical editorial need as the project approaches the end of its term. The
edition citation is retained, and the contributions list is unchanged.

**Response to the reviewer:** We made the selection rationale explicit: the corpus offers a
manageable initial case with enrichment challenges relevant to other Academy editions, while
collaboration with its editorial team supports a concrete enrichment task near the end of the
project's term. We also explain its role in identifying requirements for subsequent adaptation
of the workflow to other editions.

**Status:** Addressed in the local working tree; I7 is marked complete.
