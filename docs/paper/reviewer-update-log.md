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
