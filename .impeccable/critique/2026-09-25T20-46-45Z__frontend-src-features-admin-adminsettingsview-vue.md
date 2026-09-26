---
target: frontend/admin branding/instance settings
total_score: 24
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
target_identity: "file:/home/westphal/Projekte/BBAW/gendertagger/repo/gendertagger/frontend/src/features/admin/AdminSettingsView.vue"
target_fingerprint: "sha256:ef4f7cafb57a567286269c2b961d18f1cbe7adb68ec18c436ffe732d4e6622ce"
target_path: /home/westphal/Projekte/BBAW/gendertagger/repo/gendertagger/frontend/src/features/admin/AdminSettingsView.vue
timestamp: 2026-09-25T20-46-45Z
slug: frontend-src-features-admin-adminsettingsview-vue
---
Method: dual-agent (A: BrandingDesignReview · B: BrandingEvidenceScan)

# Critique — admin branding and instance settings

**Target:** `frontend/src/features/admin/AdminSettingsView.vue`  
**Live surface:** `/admin/settings`

## Design Health Score

| # | Heuristic | Score | Key issue |
|---|---|---:|---|
| 1 | Visibility of System Status | **2/4** | Loading, revision, override, and saving states exist, but an invalid submission gives no visible feedback at the action row and a successful save has no nearby confirmation. |
| 2 | Match System / Real World | **2/4** | The model is accurate, but “override,” “deployment fallback,” “revision,” and “same-origin URL” expose infrastructure language to publication administrators. |
| 3 | User Control and Freedom | **3/4** | Leave unchanged, clear, discard, conflict recovery, and confirmed reset provide good exits. There is no post-save undo. |
| 4 | Consistency and Standards | **3/4** | Shared typography, tables, controls, and states are coherent. Radio inputs incorrectly inherit text-field sizing, and the reset card creates a second hierarchy inside the editor. |
| 5 | Error Prevention | **3/4** | Safe defaults, validation, revision protection, conflict reconciliation, and reset confirmation are strong. The public consequence of a change is not previewed. |
| 6 | Recognition Rather Than Recall | **3/4** | Fallbacks stay visible beside fields, but users must map the overview table to a duplicate editor farther down the page. |
| 7 | Flexibility and Efficiency | **2/4** | Sparse multi-field updates are supported, but there is no row-to-editor jump, in-place editing, changed-fields summary, or persistent action area. |
| 8 | Aesthetic and Minimalist Design | **2/4** | The interface is calm, but six facts appear twice and all 18 mode choices remain visible. The 320px page is more than 4,300px tall. |
| 9 | Error Recovery | **2/4** | Field errors are specific and correctly associated, but the tested invalid submission left the first error roughly 1,164px above the viewport without moving focus. |
| 10 | Help and Documentation | **2/4** | Mechanics are described inline, but deployment-owned empty states provide no route to configuration guidance or responsible ownership. |
| **Total** |  | **24/40** | **Acceptable — trustworthy foundations, laborious interaction.** |

## Design Specificity Verdict

**Functionally authored for gendertagger; visually and interactionally under-authored.**

The information model is unmistakably product-specific: effective publication values, deployment fallbacks, explicit clearing, stored overrides, revisions, conflicts, and deployment-owned facts support gendertagger’s evidence-led scholarly identity.

The composition is category-interchangeable: heading, notice, precedence card, comparison table, long generic form, then three equal read-only cards. It never connects a proposed edit to the public footer, legal notice, home identity, or publication accountability that the edit changes. The surface feels like a correct configuration schema rather than a confident publication-control interface.

### Deterministic scan

- Target CLI scan: **0 findings**, exit code `0`, exact output `[]`.
- Live injected scan found one real but **out-of-scope** shared-shell issue: `transition: width` in `frontend/src/app/AppSidebar.vue`.
- The injected `dark-glow` warning was a **false positive caused by the detector overlay itself** and disappeared when overlay styles were removed.
- Injection succeeded, but the browser session was headless and then closed. **No persistent user-visible overlay is available.**

The deterministic detector therefore found no target-specific styling violation. The important defects are interaction and information-architecture problems that require browser evidence rather than static pattern matching.

## Overall Impression

This is a careful, honest implementation wrapped in an unnecessarily exhausting editing model. It earns trust through explicit state, safe revision handling, and truthful “not configured” values. Its biggest opportunity is to make that same truth model directly editable and consequentially legible instead of duplicating it in a second always-open form.

## Cognitive Load

**6 of 8 checks fail — high cognitive load.**

- **Single focus — fail:** overview, precedence, refresh, editing, reset, and deployment facts share one continuous page.
- **Chunking — fail:** six fields form one uninterrupted editor.
- **Grouping — pass:** sections, fieldsets, table semantics, and deployment cards are structurally clear.
- **Visual hierarchy — fail:** refresh is prominent near entry; Save sits several viewports below.
- **One thing at a time — fail:** every field, mode, reset state, and instance fact remains expanded.
- **Minimal choices — fail:** six sibling field decisions expose **18 mode radios** at once.
- **Working memory — pass:** current fallback values are repeated beside each field.
- **Progressive disclosure — fail:** untouched fields and read-only controls remain fully rendered.

At 320px, the document measured **4,331px** tall and the editor alone **2,312px**. This is not a reflow failure—the page correctly avoids document-level horizontal scrolling—but it is a substantial traversal cost.

## Emotional Journey

1. **Arrival:** calm, serious, and credible.
2. **Orientation peak:** resolution order, revision, effective values, and explicit inherited states establish trust.
3. **Editing valley:** the concise overview becomes a repetitive six-field schema editor.
4. **High-stakes moment:** revision safety reassures technically, but there is no concise “what will change publicly” review.
5. **End-state valley:** discard works silently; invalid submission appears inert; successful save has no nearby completion message.

## What’s Working

1. **The truth model is excellent.** The four-column table distinguishes human labels, stable field keys, effective values, fallbacks, and override status without relying on color.
2. **Safety is designed into the workflow.** Unchanged is the default, updates are sparse and revision-protected, drafts can be discarded, conflicts retain work, and reset is separately confirmed.
3. **Responsive and semantic foundations are strong.** At 1440px, 390px, and 320px there was no page-level overflow. The wide table becomes a named, keyboard-focusable scroll region with a visible hint. German copy wraps without clipping.

## Priority Issues

### 1. [P1] Submission feedback fails where confidence is most needed

**Why it matters:** On the live 320px flow, Save was activated with one invalid field. Focus remained on `BODY`, while the first error appeared approximately **1,164px above the viewport**. A sighted keyboard or mobile user receives no indication of what failed. Successful saves likewise reset the editor without a nearby success acknowledgement.

**Evidence:** `frontend/src/features/admin/AdminSettingsEditor.vue:201-208,302-347`; `frontend/src/features/admin/AdminSettingsView.vue:109-117`.

**Fix:** Focus and scroll to the first invalid control; add an announced error summary beside the action row with linked field names; retain inline errors. Keep a persistent status row showing “No changes,” “1 field changed,” “Saving,” or “Saved as revision N,” and distinguish a confirmed private save from a failed public refresh.

**Suggested command:** `/impeccable harden`

### 2. [P1] The overview and editor duplicate one model into a 4,300px mobile task

**Why it matters:** Users understand a field in the comparison table, then must scroll to and rediscover it in a second complete representation. A one-field correction exposes every field, 18 radios, six value controls, reset, and deployment context before completion.

**Evidence:** `frontend/src/features/admin/AdminSettingsView.vue:289-344`; `frontend/src/features/admin/AdminSettingsEditor.vue:278-333`.

**Fix:** Make the trustworthy summary the edit surface: editable rows on desktop and stacked records on mobile, with untouched records collapsed until activated. A lower-risk alternative is an explicit “Edit branding” mode plus row-to-field jumps and a persistent changed-fields action strip. Do not hide this task in a modal.

**Suggested command:** `/impeccable distill`

### 3. [P2] Labels and control geometry expose implementation mechanics

**Why it matters:** “Override,” “fallback,” “leave unchanged,” “store value,” and “clear value” describe persistence mechanics rather than publication outcomes. The same generic “Value” label is repeated six times. At 320px, radio-label targets measured about **40.3px**, below the project’s 44px narrow-control floor, while radios inherit the full-width text-input selector.

**Evidence:** `frontend/src/features/admin/AdminSettingsEditor.vue:284-326,473-497`; `frontend/src/locales/en.json:478-533`; `frontend/src/locales/de.json:478-533`.

**Fix:** Use outcome language: **Use deployment value**, **Use a custom value**, **Publish no value**. Reveal the value control only for the custom choice, show the resulting public value inline, give each control a field-specific accessible name, and separate radio styling from text-field styling with 44px label hit areas.

**Suggested command:** `/impeccable clarify`

### 4. [P2] Deployment-managed instance facts are an unactionable dead end

**Why it matters:** Logo, initiatives, and legal entity correctly say they cannot be edited here, but an administrator responsible for publication metadata gets no answer to “where do I fix this?” Three equal “not configured” cards look like a broken installation rather than a guided state.

**Evidence:** `frontend/src/features/admin/AdminSettingsView.vue:353-417`; locale blocks at `frontend/src/locales/en.json:567-587` and `de.json:567-587`.

**Fix:** State who or what owns each value, link to deployment configuration guidance, identify the public surface affected, and offer a safe “View public page” or logo preview. When all three are absent, lead with one guided empty state rather than three equal empty cards.

**Suggested command:** `/impeccable onboard`

## Persona Red Flags

### Alex — power administrator

- Finds a field in the table but cannot edit it there or jump to its editor.
- A one-field update still requires traversing all six fieldsets.
- Save is below the sixth field with no sticky action strip or changed-fields summary.
- Sparse multi-field save is powerful, but the always-open presentation hides that efficiency.

### Sam — keyboard, screen-reader, and low-vision administrator

- Invalid submission does not focus or scroll to the failing field.
- Six textboxes share the accessible label “Value”; fieldset context helps linear reading, but a controls list remains ambiguous.
- Radio-label targets fall below the project’s 44px mobile target.
- The comparison table is correctly named and hinted, but comparison still requires horizontal manipulation before editing.

### Jordan — first-time institutional administrator

- Must translate “override,” “deployment fallback,” “revision,” and “same-origin URL.”
- “Clear value” does not explain whether the public page hides the value, reveals a fallback, or removes stored data.
- The page does not identify where institution name, editors, contact, privacy URL, or publication year appear publicly.
- Deployment-managed empty cards provide no next step.

## Minor Observations

- “Discard draft” remains enabled when no draft exists, weakening its meaning.
- The reset panel is a rounded card nested inside the rounded editor, adding weight to a currently unavailable secondary action.
- The horizontal-scroll hint appears after the table; narrow users discover hidden columns only after traversing it.
- Stable API field keys are useful for support, but permanently showing all six duplicates labels for ordinary administrators.
- The account control creates a second mobile header row with substantial empty space.
- Longer German labels fit at 320px, and status pills always include text rather than relying on color.

## Questions to Consider

1. Is the primary operator a deployment engineer or a scholarly publication administrator—and should the interface speak in infrastructure terms or publication outcomes?
2. If the comparison table already contains the truth needed to decide, why is editing a separate representation rather than a state of the same record?
3. After Save, should the administrator verify the stored revision, the effective public value, the actual public surface, or all three?
4. Is explicit clearing common enough to occupy one-third of every field’s visual attention, or should it be a deliberate secondary action?
