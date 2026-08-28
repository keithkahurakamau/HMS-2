# Frontend Redesign: Calm Clinical Instrument

**Date:** 2026-08-28
**Status:** Approved direction, pending spec review
**Branch:** `feat/frontend-redesign` off `development`, single PR into `development`

## Context and goals

MediFleet's frontend spans 43 routes, 38 page files, 198 JSX files, 55 components
and 51 test suites. It already has a deliberate identity (brand cyan, teal and
emerald, Inter with Fraunces and JetBrains Mono, a 748 line `index.css`
foundation, workspace only dark mode). The problem is not the identity. It is
craft consistency: pages hand roll their own tables, toolbars, tabs and modals;
density is undifferentiated between marketing and clinical surfaces; empty,
loading and error states are inconsistent; colour is used decoratively so it no
longer reads as clinical signal; motion is ad hoc.

**Goal.** Refine, do not replace. Keep the identity and every behaviour, raise
the craft floor across every surface, and rework layout on the specific pages
where the current layout is genuinely poor.

**Non goals.** No new visual identity. No information architecture rework (how
modules are grouped, what lives on which screen, how a clinician moves through a
visit are all out of scope). No new features. No backend changes.

**Decisions taken by the user:**

1. Refine the existing identity rather than replace it.
2. Visual work plus layout rework where the layout is weak.
3. One branch, one merge, rather than staged PRs.
4. Correctness over line count: split files where the redesign genuinely needs
   it, never merely to satisfy a line limit, and everything must still work.
5. No em dashes anywhere, in UI copy or elsewhere in the frontend.

## Design tokens and foundations

### Density

Two densities, chosen per surface rather than per component.

| Token | Comfortable (marketing, portal, auth) | Compact (clinical, admin, superadmin) |
|---|---|---|
| Control height | 40px | 32px |
| Table row height | 56px | 40px |
| Card padding | 24px | 16px |
| Section gap | 32px | 20px |

Density is applied by a wrapper class on the layout, not by prop drilling into
every component.

### Type scale

Six steps, applied everywhere: 12, 14, 16, 20, 24, 32. Inter for all UI text.
Fraunces confined to marketing display and page titles. JetBrains Mono for
identifiers, codes and timestamps. `font-variant-numeric: tabular-nums` is
mandatory on every table cell, vital sign, money figure and count.

### Colour

Cyan `#0891b2` is the primary action and the active navigation state, and is
used for nothing else. Amber, red and emerald carry clinical and financial
status only, never decoration. Page backgrounds move to quiet neutral so status
colour reads. Semantic aliases are added to `tailwind.config.js` so pages stop
reaching for raw palette steps.

### Elevation

Border first. Shadow is reserved for surfaces that genuinely float: modals,
popovers, dropdowns, toasts. Decorative card shadows are removed. `.card-glass`
survives on marketing surfaces only.

### Motion

Per `emil-design-eng`: transform and opacity only, 150 to 200ms for state
changes, CSS transitions rather than keyframes so interactions stay
interruptible, springs only where a gesture drives the surface, origin aware
popovers, never animating from `scale(0)`, and `prefers-reduced-motion` honoured
throughout.

## Component rules

### Foundation changes

- `tailwind.config.js`: density scale, trimmed radius and shadow scales,
  semantic colour aliases, tabular numeral support.
- `index.css`: the two drifted `@layer components` blocks (currently at lines 66
  and 618) merge into one. `.card`, `.btn`, `.input`, `.badge`, `.tab-pill` and
  `.table-clean` are restated against the new tokens. New `.skeleton`, `.field`
  and `.empty` are added. Focus ring is unified.

### Shared primitives

Reworked: `PageHeader`, `StatTile`, `EmptyState`.

Added, because 25 module pages currently hand roll each of these differently:
`Table`, `Toolbar`, `Tabs`, `Modal`, `Field`.

Every primitive must define default, hover, focus-visible, active, disabled,
loading and error states where relevant, and must behave for keyboard, pointer
and touch.

### Required states

Every collection surface (table, list, board, panel) must ship four states:
empty, loading skeleton, error, and permission denied. The `ModuleGuard` denial
path in particular is currently abrupt and gets a designed state.

## Surfaces

### Restyle only, structure preserved

Appointments, Billing, Calendar, Cheques, Dialysis, Inventory, Maternity,
Messages, Radiology, Theatre, Triage, Wards, QueueBoard, Profile, Branding,
MpesaSettings, Support, ChangePassword, plus Login, ForgotPassword,
ResetPassword and the patient portal.

### Layout rework

`Accounting.jsx` (3,248 lines), `Patients.jsx` (1,962), `ClinicalDesk.jsx`
(1,360), `Pharmacy.jsx` (1,208), `Laboratory.jsx` (918), `AdminDashboard.jsx`
and `Settings.jsx`. These are tab walls in single files. Where the redesign
needs it, tabs are extracted into per tab components following the convention
already established in `pages/clinical/` and `pages/dialysis/`. Extraction is a
means to make the redesign tractable, not a line count exercise, and behaviour
must be identical after it.

### Marketing

Landing, Home and Demo keep `WebGLHero` and `PremiumBackground`, and adopt the
type and spacing system so they stop diverging from the app.

### Superadmin

Keeps its separate identity per `design-system/medifleet-superadmin/MASTER.md`
and its independent theme, but adopts the shared primitives so a fix does not
have to be made twice.

## Content and tone

- **No em dashes.** 1,113 occurrences across 155 files in `frontend/src` are
  rewritten in context using a colon, comma, parentheses or a full stop as the
  sentence requires. They are not blanket replaced with a hyphen, which would
  read worse. En dashes in numeric ranges are left alone.
- An `impeccable clarify` pass over labels, error messages and empty state copy.
  Factual clinical copy is not changed without asking.

## Accessibility acceptance criteria

- Text and interactive elements meet WCAG 2.2 AA contrast in both light and dark.
- Every interactive element has a visible `:focus-visible` state using the
  unified ring.
- Keyboard paths through each redesigned page remain complete: tab order is
  logical, modals trap focus and restore it on close, no interaction is pointer
  only.
- `prefers-reduced-motion: reduce` removes non essential motion.
- Status is never communicated by colour alone; it carries an icon or a label.

## Verification

1. All 51 Vitest suites green.
2. ESLint run explicitly (`vite build` does not surface `no-undef`).
3. Playwright screenshots before and after at 1440 and 390 wide, light and dark,
   for every redesigned route, as the acceptance evidence.
4. Manual keyboard pass on the reworked pages.
5. `impeccable-finish-reviewer` subagent over the finished branch.

## Anti-patterns, explicitly prohibited

- Decorative shadows on non floating surfaces.
- Cyan used for anything other than primary action and active nav.
- Status conveyed by colour alone.
- Proportional numerals in tables or vitals.
- Animating `width`, `height`, `top` or `left`; animating from `scale(0)`.
- Changing clinical copy, field labels or units without asking.
- Removing or renaming test hooks (`data-testid`, accessible names) during a
  restyle.

## QA checklist, executable in review

- [ ] No em dash in `frontend/src`.
- [ ] No raw hex outside `tailwind.config.js` and `index.css`.
- [ ] Every table uses the shared `Table` primitive and tabular numerals.
- [ ] Every collection surface has all four states.
- [ ] Every interactive element has a visible focus state.
- [ ] Contrast AA in light and dark on every redesigned route.
- [ ] Vitest green, ESLint clean.
- [ ] Before and after screenshots attached for every redesigned route.

## Delivery

Single branch `feat/frontend-redesign` off `development`, single PR into
`development` per the promotion flow. Frontend only, so the path filtered
`migration-check` workflow does not run and the merge needs the admin route.
