# Global header content brief

## Accepted direction — 2026-09-25

The user approved short breadcrumbs in the header and moved project switching into the sidebar.
The visible account name opens Personal settings and Sign out. This replaces the earlier H0 proposal
and implements H1 from the [frontend improvement plan](27-frontend-improvement-plan.md), ahead of the
individual view improvements. The Annotated Archive visual language and existing contracts remain.

**Purpose:** show where the user is within the current project or application, while keeping account
access and mobile navigation available. The header does not own the page's task or scientific context.
This is an operational surface: success means correct orientation and predictable access during work.

## Content ownership

| Content                                                  | Owner and behavior                                                                                                                                                                     |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Location                                                 | Private navigation uses breadcrumbs for the authorized project or application destination. Public pages use the home brand and their own page heading.                                 |
| Project switching                                        | Sidebar, above project destinations, on readable project routes. Global pages use Projects.                                                                                            |
| Account identity                                         | Header button shows the full display name; its menu contains Personal settings and Sign out.                                                                                           |
| Mobile navigation                                        | Eligible signed-in sessions get the sidebar drawer trigger. Public sessions have no empty drawer.                                                                                      |
| Product identity                                         | Sidebar brand for private navigation; a header home link names `gendertagger` for public/session-access pages.                                                                         |
| Language, theme, desktop collapse                        | Eligible sessions use the sidebar footer. Public/session-access pages keep language and theme in a compact header; collapse is unavailable there. Preference persistence is unchanged. |
| Page title, filters, actions, editable inputs            | Relevant view; one H1 per page.                                                                                                                                                        |
| Snapshot, run, aggregation, evaluation/export provenance | Relevant view; no persistent scientific identifier chain in the header.                                                                                                                |
| Person and annotation context                            | Review/person detail keeps TEI identity, evidence, decisions and history together.                                                                                                     |
| Working aggregation                                      | Project overview owns selection (ADR-0035); task pickers mark it as recommended without automatic selection. Scientific task context stays in the selected view. |
| Session initialization, retry and logout failure         | Header account area; existing recovery dialog owns mid-task authentication.                                                                                                            |
| Progress, save errors, conflicts and partial results     | The view or control performing the operation.                                                                                                                                          |

No new search, notifications, job centre, status summary, avatar or project selector is introduced in the
header. Account settings remain distinct from administrative branding settings.

## Breadcrumb rules

Use real navigable ancestry, limited to resources already identified by the route. Ancestors are links;
the current destination is ordinary text with `aria-current="page"`. Separators are decorative. Names
wrap, including long German project and account names, without requiring hover to read them.

| Route family                                    | Breadcrumb example                                                               |
| ----------------------------------------------- | -------------------------------------------------------------------------------- |
| Signed-in global destination                    | Projects, Personal settings, Accounts, Legal notice, or the relevant destination |
| Project overview                                | Full project name                                                                |
| Review, people, import, aggregation, membership | Project name › Current destination                                               |
| Snapshot runs, evaluations, exports             | Project name › Current collection                                                |
| Run detail                                      | Project name › Runs › Run                                                        |
| Evaluation/export detail                        | Project name › Evaluations/Exports › Evaluation/Export                           |
| Management-only membership                      | Projects › Project membership                                                    |

The run parent comes from the route's snapshot identifier; evaluation/export parents use its run
identifier. Review and aggregation routes do not fetch a run or snapshot merely to lengthen the trail.
Resource identifiers remain with their view. Breadcrumbs supplement the sidebar's primary navigation;
they do not add a second row of tabs or replace the page heading.

## Data, access and transitions

Project identity uses the route `projectId` and the existing principal-scoped `useProject` query. Only a
successful matching response with a readable project role supplies the name. The header and sidebar
share this source. A new route/account, pending request or failed query cannot display a previous
project's name. A transient failure offers Retry; forbidden/missing context offers Projects without
inferring why the API denied access. A management-only membership route retains generic scope and does
not imply that membership access itself failed. On the membership route, the shared membership-state
read establishes management authority and any ordinary project role before the shell requests readable
project identity. Management alone exposes a Members destination without scientific project navigation.
Members has its own active state; it never highlights Overview. No managed-project pagination is added
for decoration.

Project alternatives use the first server-ordered page of `useProjectList`, with loading, empty and
retry states. The Projects destination directly above the switcher opens the full list; the quick menu
does not duplicate that link. A failed alternatives read does not erase the separately authorized
current name. Switching opens the target project's overview without transferring old filters or resource IDs.
The menu is bounded by the viewport and repositions on scrolling/resizing. Desktop renders its popup
through a body portal so the sticky sidebar cannot trap it beneath page content. Mobile retains the
popup inside the drawer's focus boundary. Crossing into mobile closes the desktop popup. The collapsed
rail uses an accessible icon button and project-naming tooltip.

Session resolution, anonymous, failed initialization, password-change-required, and ready states remain
distinct. Private controls wait for an eligible session. Forced password change keeps account identity
and Sign out available. Logout failures keep the current account and unsaved input visible with Retry;
only confirmed logout or an already-anonymous response clears the session. Late responses must not clear
a replacement session or redirect its user. Principal changes close account/project overlays and clear
prior-account input. Same-account recovery preserves eligible drafts.

## Unsaved work

A per-application registry holds view-owned dirty checks and discard callbacks, never draft contents.
Path or resource-parameter navigation, including breadcrumbs and switching, prompts **Stay / Discard and
leave** when a registered draft exists. Stay and failed/cancelled navigation preserve input. Discard runs
only after successful navigation; sign-out asks before its request and discards only after success.
There is no implicit save or resubmission.

Coverage includes review decisions and bulk input, import, project/run/aggregation/evaluation/export
creation, personal settings, branding, account create/edit and team create/rename. Search/filter controls
and immediate membership commands are not drafts. Successful saves establish a clean baseline; failed
saves remain dirty. Departed/discarded views ignore late results that would restore input or redirect.

Submitted jobs and saved decisions remain persisted. Leaving an active bulk review stops subsequent
people after the current submission; it does not abort or roll back the current write. Ordinary query
and hash changes retain their existing navigation semantics. Same-person review filter refreshes keep
the detail mounted. Changing or clearing the selected person in a review query also prompts before
discarding its draft, including queue changes that clear the selection. Browser tab closure remains
outside this in-application navigation guard's scope.

## Responsive composition and verification

An eligible session (`canUsePrivateNavigation`) uses the sidebar and breadcrumb header. Signed-out,
unresolved, failed-session and password-change-required states use the full content width without a
sidebar or drawer trigger. Their header contains the home brand, account/sign-in/session feedback and
the existing preference controls in a compact horizontal presentation. On the signed-out home page, an inline sign-in form (username, password, submit; success continues to
the projects, or to the forced password change) replaces the header link, and the header omits its
duplicate link and empty account slot. The login page omits the header link as well. Other
public pages retain the header sign-in entry, and session loading/error feedback remains available on
every route. At narrow widths the preferences
wrap into a full-width second row. Menus open downward; temporary and anonymous preference behavior is
unchanged. Legal/publication links remain in the footer. Login restores private navigation, and logout
removes it without changing the saved desktop-collapse preference.

For private navigation, desktop uses breadcrumbs followed by the account control. Narrow screens use
navigation and breadcrumbs in the first row, with the account control beneath. The DOM and reading order agree. Menus, failures and
long labels can wrap; the header is not sticky. The project switcher moves with the sidebar into its
mobile drawer. Broader sidebar grouping and animation changes remain S1.

Automated verification covers both locales, route ancestry, long names, loading/retry/access loss,
principal changes, menu semantics, drawer placement, session failures and draft navigation. The current
implementation and outstanding live checks are recorded in the [improvement plan](27-frontend-improvement-plan.md).
Rendered desktop/mobile geometry, enlarged text, keyboard visibility and assistive-technology checks
remain required; component tests do not substitute for them.
