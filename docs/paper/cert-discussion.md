# @CERT

## Claude

Yes, and it's more than confusing wording. The paper contradicts itself, because "cert" refers to three different scales:

| Scale | Values | Role |
|---|---|---|
| LLM self-reported certainty (`llm_cert`) | `high`, `low`, `uncertain` | Input to the tier |
| Internal certainty tier | `high`, `low`, `contested`, `single`, `uncertain` (the backend adds `no_data`) | Derived from method agreement, authority overrides and `llm_cert` |
| TEI `@cert` | `high`, `low`, `unknown` | Converted from the tier during export |

This goes back to the prototype, which stored the internal tier in a column called `cert` (`data/output/gender_summary.csv`), and the paper kept that name.

**Where the paper mixes them:**
- [Line 169](docs/paper/article.tex#L169) describes TEI `@cert`, but it maps straight from method agreement. It leaves out the two tiers for entries only the LLM classified (`single`, `uncertain`): 1,048 entries, or 12.7%. It also reads as if TEI allowed only three values, but TEI defines `high`, `medium`, `low` and `unknown`.
- [Line 234](docs/paper/article.tex#L234) names internal tiers `high` and `low`, the same words as the TEI values.
- [Line 363](docs/paper/article.tex#L363) calls the internal tiers "the TEI `@cert` values written into the final output" and lists `contested`, `single` and `uncertain`. That contradicts line 169, and these aren't valid TEI values.
- The disagreement-examples table ([line 400](docs/paper/article.tex#L400)) writes "cert `high`" and "cert `single`" for the internal tier.
- [Line 472](docs/paper/article.tex#L472) uses `cert` for the LLM's own output field.

**The two implementations also differ, and the paper's example matches neither the current code nor line 169:**
- **Prototype:** its export script (`scripts/enrich_sex.py` in commit `31a5273`) produced the case-study TEI. It keeps `high` and turns every other tier into `low`. The tagged register in `data/raw` has 6,865 `high`, 628 `low` and no `unknown`.
- **Current backend** ([certainty_projection.py](backend/src/gendertagger/export/certainty_projection.py), [docs/08](docs/08-ingestion-and-export.md#L248)): `high` stays `high` and `low` stays `low`; every other tier becomes `unknown`. Human-reviewed entries always become `high`.
- **Example entry S0001126** has tier `single` (LLM only). The prototype wrote `cert="low"`, which is what the paper shows. The backend would write `unknown`, and line 169 doesn't cover this case.

**Suggested fix for I13:**
1. Use three distinct names throughout: "LLM self-reported certainty", "certainty tier" and "TEI `@cert`". Never call the tier "cert".
2. Correct line 363 to say that agreement tiers map onto certainty tiers, not onto TEI values.
3. Replace the prose at line 169 with a complete conversion table from certainty tier to TEI `@cert`, including the LLM-only tiers and human review.
4. Answer the reviewer's "another scale?" question directly. The finer tier is kept: the backend's CSV export has `agreement_tier` and `certainty_tier` columns, and TEI gets a coarser version. A numeric `<certainty degree="…">` would suggest calibrated probabilities, which the method confidences aren't. Also say why `medium` isn't used.

**Decision for you:** which of the two mappings should the paper describe? I'd pick the backend's, because the TEI section already describes the backend's `<gender>` model (the prototype wrote `<sex>`). That means changing the example to `cert="unknown"` and rewording the sentence below it. This also depends on the open question of which code version the paper cites. Changing the backend's mapping instead would require a design-doc update and an ADR.

Should I draft the I13 changes on that basis?

## ChatGPT

I think **I13 needs a clearer definition and justification of the existing scheme**. We can address it through targeted paper edits.

The central distinction is that **`@cert` expresses the workflow’s assessment of an annotation’s support—not a calibrated probability that it is correct**. For example, 75% agreement between methods does not establish 75% accuracy.

The [implemented rules](/home/westphal/Projekte/BBAW/gendertagger/repo/gendertagger/backend/src/gendertagger/domain/aggregation_assessment.py:116) and [TEI projection](/home/westphal/Projekte/BBAW/gendertagger/repo/gendertagger/backend/src/gendertagger/export/certainty_projection.py:11) give us this explanation:

| Exported `@cert` | How it is assigned |
|---|---|
| `high` | At least two pooled methods vote and the winning label receives ≥75% agreement; alternatively, an authority override applies or an editor reviews the annotation. |
| `low` | A decided pooled vote receives ≥50% but <75% agreement, with at least two voters. |
| `unknown` | The internal assessment is `contested`, `single`, `uncertain`, or `no_data`. |

An unresolved substantive tie remains contested. These mappings apply where an annotation is exported; records without a resulting label do not automatically receive a new `<gender>` element.

Two points need particular care:

- **Authority overrides receive `high` even when other methods disagree.** The manuscript currently contradicts itself on this. We should correct the passages that require agreement with the vote.
- **`value="unknown"` and `cert="unknown"` describe different things:** the classification result versus its certainty. Human review assigning `high` is also an editorial policy, not a guarantee of correctness.

The research gives us useful comparisons:

- **TEI provides a broader vocabulary.** Its qualitative values include `high`, `medium`, `low`, and `unknown`; `unknown` means that the encoder does not assert a certainty judgment. Our three values are therefore a **project-specific subset**. [TEI certainty datatype](https://www.tei-c.org/release/doc/tei-p5-doc/en/html/ref-teidata.certainty.html)
- **Numerical alternatives are possible.** TEI permits numerical probabilities in `@cert`, and `<certainty degree="…">` can describe confidence in a particular aspect of an annotation. That does not justify treating our agreement score as a probability. [TEI probability/certainty datatype](https://www.tei-c.org/release/doc/tei-p5-doc/en/html/ref-teidata.probCert.html), [structured uncertainty](https://www.tei-c.org/release/doc/tei-p5-doc/en/html/CE.html#CECERTAINTY)
- **EpiDoc demonstrates qualitative editorial practice:** `cert="low"` marks tentative restorations or uncertain abbreviation expansions, attached to the specific interpretation concerned. [EpiDoc guidelines](https://epidoc.stoa.org/gl/latest/trans-abbrevuncert.html)
- **PROVIDEDH demonstrates a finer scale:** human uncertainty judgments use a five-point Likert scale, alongside categories describing the source or nature of uncertainty. This illustrates why degree and reason should remain distinguishable. [Edmond et al. 2023, §§31–34](https://www.digitalhumanities.org/dhq/vol/17/3/000701/000701.html)

My recommendation is to retain the current scale and explain it as a compact aid to editorial review, while preserving the more detailed internal assessments. Specifically:

1. Revise the existing `@cert` description to give the complete mapping and its meaning.
2. Add a short paragraph comparing our choice with TEI’s alternatives, EpiDoc, and PROVIDEDH.
3. Correct the authority-override inconsistency and passages that call internal tiers such as `single` TEI values.

That answers all four parts of I13 without introducing a new scoring system. No files changed.
