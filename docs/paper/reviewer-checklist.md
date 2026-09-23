# Paper revision checklist

Line numbers refer to the submitted manuscript. This checklist records the reviewers' requests
separately from issues found during our own audit. Completed changes are documented in the
[reviewer update log](reviewer-update-log.md).

## Editorial requirements

- [ ] Submit the revised manuscript within four weeks of receiving the decision email.
- [ ] Provide a detailed, point-by-point list of changes responding to the reviews.

## Reviewer C: written report

- [ ] Fix the application startup failure: `ModuleNotFoundError: No module named 'gender_project'`.
- [ ] Make README and QUICKSTART instructions reproducible, including the missing input path
  `data/raw/schleiermacher/Register/Personen`.
- [x] Add `CITATION.cff` and cite the software repository in the bibliography.

## Reviewer C: annotated PDF

The six annotations raise four distinct issues; two comments repeat or clarify earlier annotations.
Source: [Reviewer C's annotated PDF](C-klappenbach,neuber,westphal_2026_gendertagger-comment.pdf).

- [x] **Page 6:** Expand GND at its first occurrence, with a brief explanation or link.
  (Two annotations.)
- [x] **Page 7:** Explain the maintenance tradeoff of local authority snapshots: they need updating
  to incorporate later changes.
- [x] **Page 7:** Clarify whether the parenthetical-qualifier rule is implemented within gendertagger
  or in separate code.
- [x] **Page 10:** Clarify "combined label"; consider "resulting label" or "post-voting label."
  (Two annotations.)

## Reviewer I: all 28 specific comments

- [x] **I1 - Abstract:** Consolidate the paragraphs; explain what `N = 8,277` counts and consider
  whether it belongs in the abstract.
- [x] **I2 - Line 32:** Explain "authority files." Name GND where appropriate; consider the broader
  term "terminologies" and explain the scope.
- [x] **I3 - Footnote 1:** Prevent the footnote from splitting across pages.
- [x] **I4 - Line 77:** Add a link to TEI in a footnote.
- [x] **I5 - Line 79:** Explain what "authority data queries" means.
- [x] **I6 - Line 80:** Check whether "Transformer" should be lowercase.
- [ ] **I7 - Line 83:** Explain why Schleiermacher digital was selected and what makes it suitable.
- [x] **I8 - Lines 91-97:** Consolidate into one paragraph.
- [x] **I9 - Lines 101-128:** Replace "First... Second..." with descriptive LaTeX
  `\paragraph{...}` headings.
- [x] **I10 - Line 111:** Translate `uneindeutig`.
- [ ] **I11 - Footnote 2:** Add an access date.
- [ ] **I12 - Lines 167-169:** Address the suggestion to add certainty information and a gazetteer
  link to the Gnadenfrei example.
- [ ] **I13 - Lines 186 onward:** Explain how `@cert` categories are derived, what they mean,
  possible alternative scales, and relevant DH practice.
- [x] **I14 - Lines 238-241:** Justify using GND alone and discuss alternatives such as Wikidata,
  VIAF, and Getty ULAN.
- [ ] **I15 - Footnotes 5 and 6:** Add access dates.
- [ ] **I16 - Line 306:** Move the inline link into a footnote.
- [x] **I17 - Line 347:** Translate *Tochter des ...*.
- [x] **I18 - Line 400:** Translate *Frau des ...* and *Schwester von ...*.
- [x] **I19 - Line 427:** Translate *Tochter* and *Frau des ...*.
- [x] **I20 - Line 467:** Translate *(Frau des Heinrich)*, *(Mutter der Antonie)*, and
  *(Mann der Marianne)*.
- [x] **I21 - Line 476:** Translate *(Tochter des Ernst Ferdinand Klein)*.
- [x] **I22 - Table 6:** Translate *Frau des*, *Baronin von*, *Arzt in Berlin*, and
  *wohnhaft in der Friedrichsgracht 50*.
- [ ] **I23 - Lines 532 onward:** Add a discussion connecting the case study and limitations,
  particularly the RSE implications and the possible role of NFDI/TS4NFDI.
- [ ] **I24 - Footnotes 9 and 10:** Add access dates or convert them into bibliography entries
  for software visibility.
- [ ] **I25 - Line 551:** Clarify "§4," for example by writing "Section 4."
- [ ] **I26 - Line 588:** Identify the model names and purposes for both writing assistance and
  code generation.
- [ ] **I27 - Footnotes 11-14:** Add access dates.
- [ ] **I28 - Bibliography:** Use either a DOI or a URL for each reference, avoiding duplicate links.
- [x] **Final translation check:** Check all German examples and tables for English translations,
  including phrases beyond the explicitly listed locations.

## Reviewer K: overlaps with Reviewer C

- [ ] Fix the broken imports preventing the Streamlit prototype from starting.
- [ ] Supply the missing register input or an illustrative dummy dataset.
- [ ] Verify that the README instructions can be followed successfully before publication.

Addressing a suggestion can mean making the change or explaining a justified decision in the
response letter.
