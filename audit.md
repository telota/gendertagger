
 Frontend audit

 Result: 12/20 — Acceptable

 Strong semantic, theming, and code-splitting foundations. The main risks are keyboard bypass, light-theme error contrast, and mobile reflow in the primary review workflow.

 ┌──────────────────────────┬───────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
 │ Dimension                │ Score │ Assessment                                                                                                                           │
 ├──────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ Accessibility            │ 2/4   │ Good semantic baseline, but one WCAG Level A failure, one AA contrast failure, and invalid ARIA on keyboard hints                    │
 ├──────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ Performance              │ 3/4   │ Route-split bundle, no measured long tasks or layout shift; one layout-affecting width animation                                     │
 ├──────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ Theming                  │ 3/4   │ Complete light/dark token system and pre-paint initialization; one real foreground/background pairing is missing from contrast tests │
 ├──────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ Responsive design        │ 1/4   │ Most screens fit 320–768px, but the primary review view overflows at phone widths and text scaling exposes another route failure     │
 ├──────────────────────────┼───────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
 │ Implementation integrity │ 3/4   │ Coherent component system with isolated detector warnings and product-name drift                                                     │
 └──────────────────────────┴───────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

 Verification performed

 - impeccable detect --json frontend/src
   - 2 warnings: layout-transition, side-tab
 - Production build:
   - Succeeded, 1,942 modules in 1.54s
   - Main JS: 333.52 kB raw / 99.68 kB gzip
   - Review route: 44.92 kB raw / 12.49 kB gzip
 - Live browser audit:
   - Routes: home, projects, review, admin users, admin settings, user settings
   - Viewports: 320×568, 390×844, 768×1024, 1440×1000
   - Light and dark themes
   - Text-only scaling at 200%
 - Axe:
   - 0 confirmed violations on all six light-theme routes
   - 0 confirmed violations on sampled dark-theme routes
   - One serious incomplete result affecting four <kbd> elements
 - Runtime sample:
   - No console errors on home, review, or admin settings
   - Review navigation: FCP 616 ms, CLS 0, no long tasks
 - No code changed.

 P0 — Critical

 None.

 P1 — High priority

 ### A11Y-01: No bypass for repeated application navigation

 Location: frontend/src/app/App.vue:23-35

 The shell renders the sidebar and header before each route without a skip link. On the review route, keyboard users traverse 18 focusable elements before reaching <main>. No href="#…" bypass link exists.

 Impact: Fails WCAG 2.4.1, Bypass Blocks. This compounds across every authenticated route and every page navigation.

 Fix:

 - Add the first focusable element in App.vue as a “Skip to main content” link.
 - Give the routed-content wrapper a stable target and tabindex="-1".
 - Make the link visible on focus.
 - Preserve each route’s existing <main> landmark rather than introducing nested <main> elements.

 ### A11Y-02: Light-theme critical text misses AA contrast

 Locations:

 - frontend/src/styles/tokens.css:17,32
 - frontend/tests/styles/tokens.spec.ts:62-75
 - Page-level uses include ReviewDetail.vue:362-377 and AdminUserDirectoryView.vue:424-439

 Measured pairing:

 - --critical: #d03b3b
 - --page: #f2f1ee
 - Contrast: 4.254:1
 - Required for normal text: 4.5:1

 The current token test verifies critical on panel, but not critical on page, despite page-level errors using that combination.

 Impact: Error and destructive-state text can fail WCAG 1.4.3 in the default light theme.

 Fix:

 - Prefer a distinct --critical-text token if the existing token must continue serving as borders and filled-control backgrounds.
 - Test critical-text/page and critical-text/panel in both themes.
 - Also retain tests for inverse text used on destructive filled buttons.

 ### RESP-01: Primary review workflow causes document-level horizontal scrolling

 Locations:

 - frontend/src/features/review/ReviewDetail.vue:131-186
 - frontend/src/features/review/ReviewDetail.vue:280-300
 - frontend/src/features/review/ReviewDetail.vue:329-350

 Observed:

 ┌──────────────────┬──────────────┬────────────────┐
 │ Viewport/state   │ Client width │ Document width │
 ├──────────────────┼──────────────┼────────────────┤
 │ 320px            │ 320px        │ 470px          │
 ├──────────────────┼──────────────┼────────────────┤
 │ 390px            │ 390px        │ 470px          │
 ├──────────────────┼──────────────┼────────────────┤
 │ 390px, 200% text │ 390px        │ 937px          │
 ├──────────────────┼──────────────┼────────────────┤
 │ 768px            │ 768px        │ 768px          │
 └──────────────────┴──────────────┴────────────────┘

 The prediction table has no contained scroll region. The fixed grid-template-columns: 9rem 1fr fact layout also expands severely when text size increases. Browser scrolling to the table automatically moved the
 document to scrollX=57; method names and confidence values could not be viewed together.

 Impact: The core review task fails WCAG 1.4.10 reflow at common phone widths.

 Fix:

 - Stack fact terms and values below the mobile breakpoint.
 - Put the prediction table in a labeled, keyboard-scrollable overflow container, following the existing admin-table pattern.
 - Provide a visual horizontal-scroll cue.
 - Ensure all intermediate flex/grid children use min-width: 0.
 - Confirm documentElement.scrollWidth === clientWidth at 320px and 390px.

 P2 — Important

 ### A11Y-03: Prohibited accessible names on <kbd>

 Location: frontend/src/features/review/ReviewDecision.vue:215-228

 Four keyboard shortcut elements use aria-label directly on <kbd>. Axe reports these as serious aria-prohibited-attr incomplete results.

 Fix: Remove the prohibited attribute. If “Key 1” rather than “1” must be announced, use adjacent visually hidden text followed by the semantic <kbd> value.

 ### RESP-02: Admin user management overflows at 200% text size

 Location: frontend/src/features/admin/AdminUserDirectoryView.vue:328-354

 At 390px with text-only scaling at 200%, the document expands to 506px. The principal contributor is .admin-user-directory-actions { min-width: 13rem; }, which becomes wider than the available content column as
 rem-based padding also increases.

 Regular 320–768px rendering passes, so this is narrower than the review failure.

 Fix: Remove the mobile minimum or constrain it with max-width: 100%/min-width: 0. Use responsive padding that leaves a viable content column at enlarged text sizes.

 ### RESP-03: Shared controls miss the 44px touch-target audit target

 Locations:

 - frontend/src/app/AppHeader.vue:89-101
 - frontend/src/app/AppHeader.vue:129-140
 - frontend/src/components/base/AppButton.vue:47-60

 Examples measured in mobile layouts:

 - Navigation menu: 40×40px
 - Standard buttons: approximately 38px high
 - Header sign-out action: approximately 19px high with no padding
 - Several select controls: 21–40px high

 Associated labels and spacing mean many controls likely satisfy WCAG 2.5.8’s 24px exception, but the interface does not meet the audit’s 44px ergonomic target.

 Fix: Establish target sizing in shared primitives, ideally min-block-size: 2.75rem, while allowing dense desktop table actions only where justified. At minimum, enlarge standalone mobile navigation and account
 actions.

 P3 — Minor

 ### PERF-01: Sidebar animates a layout property

 Location: frontend/src/app/AppSidebar.vue:66-78

 transition: width var(--sidebar-transition) triggers layout work during collapse. The animation is short and reduced-motion handling is correct, so no runtime regression was measured.

 Fix: Snap the sidebar width and animate only inner opacity/transform, or remove the transition.

 ### INT-01: Canonical lowercase product name is not implemented

 Locations:

 - frontend/index.html:6
 - frontend/src/locales/en.json:3,8
 - frontend/src/locales/de.json:3,8

 The UI and document title use Gendertagger, while the canonical product name is gendertagger.

 Fix: Normalize browser title, application title, introductions, and accessible brand text to lowercase.

 ### INT-02: Marked-block style triggers the side-tab detector

 Location: frontend/src/features/review/ReviewDetail.vue:308-315

 The authority/conflict block uses a 4px accent-only left border. This is intentional and low severity, but the same accent treatment represents authority overrides, conflicts, and prediction errors.

 Fix: Prefer a complete hairline callout boundary with explicit state modifiers, or document a narrowly scoped detector exception if the treatment is intentionally retained.

 Positive findings

 - Consistent <main> landmarks, one <h1> per audited route, valid language metadata, labeled controls, and no duplicate IDs.
 - Strong global focus indication in frontend/src/styles/base.css:26-30.
 - Reduced-motion handling preserves state changes while reducing durations.
 - Status and error states generally use role="status", role="alert", or live regions.
 - Route-level code splitting is used throughout frontend/src/app/router.ts.
 - No component-level hardcoded colors; semantic tokens are centralized.
 - public/theme-init.js resolves system/light/dark preferences synchronously before first paint and tolerates blocked storage.
 - Dark mode passed sampled live axe scans.
 - Admin tables correctly contain their own horizontal overflow rather than expanding the page.
 - No image payload or unoptimized image concerns in frontend/src.

 Systemic patterns

 1. Contrast tests lag actual token usage. Tests validate documented pairs, but not every background where a semantic token is rendered.
 2. Responsive containment is inconsistent. Admin tables have the correct scroll-container pattern; the review evidence table does not reuse it.
 3. Control sizing is compact at the primitive level. Fixing AppButton and shell controls will address many touch-target findings centrally.
 4. Accessibility work is otherwise mature. The failures are concentrated and repairable rather than evidence of missing semantics throughout the application.

 Recommended command sequence

 1. /impeccable harden — skip navigation, invalid ARIA, and critical-text contrast
 2. /impeccable adapt — review reflow, 200% text scaling, and touch targets
 3. /impeccable optimize — eliminate the layout-affecting sidebar animation
 4. /impeccable clarify — normalize the canonical lowercase product name
 5. /impeccable polish

 You can ask me to run these one at a time, all at once, or in any order you prefer.

 Re-run /impeccable audit after fixes to see your score improve.

