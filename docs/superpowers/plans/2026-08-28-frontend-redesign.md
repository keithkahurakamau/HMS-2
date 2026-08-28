# Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise the craft floor of all 43 MediFleet frontend routes while keeping the existing identity, every behaviour, and every test green.

**Architecture:** Foundation first. Tokens and `index.css` carry most of the change, because `.card` (242 uses across 67 files), `.btn-*` (237 uses) and `.badge` (173 uses) are already widely adopted, so restating them propagates everywhere at once. Then the two genuine inconsistencies get fixed structurally: 24 of 30 files with a `<table>` hand-roll their own styles, and `.tab-pill` is dead CSS with zero uses while every page hand-rolls tabs. Only then do individual pages get touched, and only seven of them get real layout rework.

**Tech Stack:** React 19, Vite 8, Tailwind 3.4 (`darkMode: 'class'`), React Router 7, lucide-react, react-hot-toast, Vitest 4 with Testing Library and MSW.

**Spec:** `docs/superpowers/specs/2026-08-28-frontend-redesign-design.md`

**Branch:** `feat/frontend-redesign` off `development`, single PR into `development`.

## Global Constraints

- **No em dashes** anywhere in `frontend/src`, in copy or comments. Colon, comma, parentheses or full stop instead. En dashes in numeric ranges are allowed.
- **Identity is fixed:** brand cyan `#0891b2`, teal, emerald, Inter, Fraunces, JetBrains Mono. Do not introduce new hues or fonts.
- **Behaviour is fixed:** no feature changes, no route changes, no API changes, no copy changes to clinical labels or units without asking.
- **Test hooks are fixed:** never remove or rename a `data-testid`, an accessible name, a label association or a role during a restyle. Tests find elements by these.
- **Cyan is only** the primary action and the active nav state.
- **Amber, red and emerald** carry clinical or financial status only, never decoration.
- **Shadows only on floating surfaces:** modals, popovers, dropdowns, toasts. Everything else uses borders.
- **Motion:** transform and opacity only, 120 to 220ms, CSS transitions rather than keyframes, never animate from `scale(0)`, honour `prefers-reduced-motion`.
- **Tabular numerals** on every table cell, vital sign, money figure and count.
- **Dark mode parity** is required on every file touched. There are 3,452 inline `dark:` variants today; a page is not done until it is checked in both themes.
- **Every task ends green:** `npm test`, `npm run lint`, `npm run build` all pass in `frontend/`.

## Commands

Run from `frontend/`:

```bash
npm test                 # full Vitest suite (51 files)
npm test -- Pharmacy     # single suite by name
npm run lint             # ESLint; vite build does NOT surface no-undef
npm run build            # production build
npm run dev              # dev server for screenshots
```

## File Structure

**Foundation (Tasks 1 to 4):**
- Modify `frontend/tailwind.config.js`: density variables, trimmed radius and shadow scales, semantic status aliases, motion tokens.
- Modify `frontend/src/index.css`: merge the two drifted `@layer components` blocks (currently at lines 66 and 618), restate primitives, add new utilities.

**New shared components (Tasks 5 to 8):**
- Create `frontend/src/components/ui/Skeleton.jsx`: loading placeholder.
- Create `frontend/src/components/ui/ErrorState.jsx`: failed load with retry.
- Create `frontend/src/components/ui/Tabs.jsx`: accessible tab list.
- Create `frontend/src/components/ui/Toolbar.jsx`: page-level filter and action bar.
- Modify `frontend/src/components/EmptyState.jsx`, `PageHeader.jsx`, `StatTile.jsx`, `ModuleGuard.jsx`.

**Pages:** restyled in batches (Tasks 9 to 13), reworked individually (Tasks 14 to 18), then marketing, auth, portal and superadmin (Tasks 19 to 21).

**Sweeps (Tasks 22 to 23):** em dashes, copy, accessibility, screenshots.

**Deliberate deviation from the spec.** The spec lists `Table`, `Modal` and `Field` as new components. They ship here as CSS instead (`.table-clean`, `.overlay-surface`, `.field`), because 24 files already contain a working `<table>` and swapping each for a component API would be a behavioural rewrite of 24 files to gain styling that a class delivers for free. `Tabs` and `Toolbar` do ship as components, because tabs need keyboard behaviour and a toolbar needs layout logic that a class cannot express.

---

## Task 1: Design tokens

**Files:**
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/src/index.css` (`@layer base`, add `:root` block after line 10)

**Interfaces:**
- Produces: CSS variables `--ctl-h`, `--row-h`, `--card-p`, `--sec-gap`, `--dur-fast`, `--dur`, `--dur-slow`, `--ease-out`; the `.density-compact` class; Tailwind aliases `h-ctl`, `p-card`, `gap-sec`, `rounded-*` (trimmed), `shadow-overlay`, `shadow-pop`, colours `status-ok`, `status-warn`, `status-critical`, `status-info`.

- [ ] **Step 1: Add the density and motion variables to `index.css`**

Insert immediately after the `@tailwind utilities;` line, before the existing `@layer base`:

```css
/* ---------------------------------------------------------------------
   Density and motion tokens.
   Comfortable is the default (marketing, portal, auth).
   Clinical and admin surfaces opt into .density-compact on their layout.
   --------------------------------------------------------------------- */
:root {
  --ctl-h: 2.5rem;    /* 40px control height */
  --row-h: 3.5rem;    /* 56px table row */
  --card-p: 1.5rem;   /* 24px card padding */
  --sec-gap: 2rem;    /* 32px section gap */

  --dur-fast: 120ms;
  --dur: 160ms;
  --dur-slow: 220ms;
  --ease-out: cubic-bezier(0.2, 0, 0, 1);
}

.density-compact {
  --ctl-h: 2rem;      /* 32px */
  --row-h: 2.5rem;    /* 40px */
  --card-p: 1rem;     /* 16px */
  --sec-gap: 1.25rem; /* 20px */
}

@media (prefers-reduced-motion: reduce) {
  :root {
    --dur-fast: 0ms;
    --dur: 0ms;
    --dur-slow: 0ms;
  }
}
```

- [ ] **Step 2: Expose the tokens in `tailwind.config.js`**

Inside `theme.extend`, add:

```js
      height: {
        ctl: 'var(--ctl-h)',
      },
      minHeight: {
        ctl: 'var(--ctl-h)',
      },
      padding: {
        card: 'var(--card-p)',
      },
      gap: {
        sec: 'var(--sec-gap)',
      },
      borderRadius: {
        sm: '0.375rem',   // 6px
        DEFAULT: '0.5rem', // 8px
        lg: '0.75rem',    // 12px
        xl: '1rem',       // 16px
      },
      boxShadow: {
        overlay: '0 12px 32px -8px rgb(2 6 23 / 0.18), 0 2px 8px -2px rgb(2 6 23 / 0.10)',
        pop: '0 6px 16px -6px rgb(2 6 23 / 0.16)',
      },
      transitionDuration: {
        fast: 'var(--dur-fast)',
        DEFAULT: 'var(--dur)',
        slow: 'var(--dur-slow)',
      },
```

Extend `theme.extend.colors` with semantic status aliases that point at hues already in the palette:

```js
        status: {
          ok:       '#059669', // accent-600
          warn:     '#d97706', // amber-600
          critical: '#dc2626', // red-600
          info:     '#2563eb', // blue-600
        },
```

- [ ] **Step 3: Verify the build compiles and nothing regressed**

Run: `cd frontend && npm run build && npm run lint && npm test`
Expected: build succeeds, lint clean, all 51 suites pass. No visual change yet, these are additive tokens.

- [ ] **Step 4: Commit**

```bash
git add frontend/tailwind.config.js frontend/src/index.css
git commit -m "feat(design): add density, motion, radius, shadow and status tokens"
```

---

## Task 2: Consolidate index.css and restate the primitives

**Files:**
- Modify: `frontend/src/index.css` (merge `@layer components` at line 618 into the one at line 66; merge `@layer utilities` at line 735 into the one at line 324)

**Interfaces:**
- Consumes: tokens from Task 1.
- Produces: restated `.card`, `.card-elevated`, `.btn`, `.btn-primary`, `.btn-secondary`, `.btn-ghost`, `.btn-danger`, `.input`, `.badge*`; new `.skeleton`, `.field`, `.empty`, `.tnum`, `.overlay-surface`.

- [ ] **Step 1: Merge the duplicated layer blocks**

Move the contents of the second `@layer components` block (line 618 onward) into the first (line 66), and the second `@layer utilities` into the first. Where the two blocks define the same selector, keep the later definition, since that is what the browser is currently applying. Delete the now-empty blocks. Make no visual change in this step.

- [ ] **Step 2: Run the suite to prove the merge was behaviour-neutral**

Run: `cd frontend && npm run build && npm test`
Expected: build succeeds, all suites pass.

- [ ] **Step 3: Commit the merge on its own, so the restyle diff stays readable**

```bash
git add frontend/src/index.css
git commit -m "refactor(css): merge duplicated @layer blocks in index.css"
```

- [ ] **Step 4: Restate `.card` to border first**

Replace the `.card` rule with:

```css
  .card {
    @apply bg-white dark:bg-ink-900 rounded-lg border border-ink-200 dark:border-ink-800;
    padding: var(--card-p);
  }
  .card-flush {
    @apply bg-white dark:bg-ink-900 rounded-lg border border-ink-200 dark:border-ink-800;
  }
  /* Reserved for genuinely floating surfaces: modals, popovers, dropdowns, toasts. */
  .overlay-surface {
    @apply bg-white dark:bg-ink-900 rounded-lg border border-ink-200 dark:border-ink-800 shadow-overlay;
  }
```

Delete `.card-elevated`'s shadow and fold it into `.card`. Keep `.card-glass` but scope it: add a comment that it is marketing only.

- [ ] **Step 5: Restate `.btn` for the density token and interruptible motion**

```css
  .btn {
    @apply inline-flex items-center justify-center gap-2 rounded-md px-4 text-sm font-semibold;
    height: var(--ctl-h);
    transition: background-color var(--dur) var(--ease-out),
                border-color var(--dur) var(--ease-out),
                color var(--dur) var(--ease-out),
                transform var(--dur-fast) var(--ease-out);
  }
  .btn:active { transform: translateY(0.5px) scale(0.99); }
  .btn:disabled { @apply opacity-50 cursor-not-allowed; transform: none; }
```

Leave the `.btn-primary`, `.btn-secondary`, `.btn-ghost` and `.btn-danger` colour rules as they are, they already read correctly.

- [ ] **Step 6: Add the new utilities**

```css
  .tnum { font-variant-numeric: tabular-nums; }

  .skeleton {
    @apply rounded bg-ink-100 dark:bg-ink-800;
    animation: skeleton-pulse 1.4s ease-in-out infinite;
  }
  @media (prefers-reduced-motion: reduce) {
    .skeleton { animation: none; }
  }

  .field { @apply flex flex-col gap-1.5; }
  .field > label { @apply text-sm font-medium text-ink-700 dark:text-ink-300; }
  .field > .field-hint { @apply text-xs text-ink-500 dark:text-ink-400; }
  .field > .field-error { @apply text-xs text-status-critical; }

  .empty { @apply flex flex-col items-center justify-center gap-3 py-12 text-center; }
```

Add the keyframes in `@layer utilities`:

```css
  @keyframes skeleton-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.55; }
  }
```

- [ ] **Step 7: Delete the dead `.tab-pill` rules**

`.tab-pill` and `.tab-pill-active` have zero uses in the codebase. Delete both. Task 7 introduces a real tab component.

- [ ] **Step 8: Verify**

Run: `cd frontend && npm run build && npm run lint && npm test`
Expected: all green. Cards will now be flatter and bordered; that is the intended change.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(design): border-first cards, density-aware controls, skeleton and field utilities"
```

---

## Task 3: Typography scale

**Files:**
- Modify: `frontend/src/index.css` (`@layer components`)

**Interfaces:**
- Produces: `.t-caption` (12px), `.t-body` (14px), `.t-body-lg` (16px), `.t-title` (20px), `.t-heading` (24px), `.t-display` (32px).

Tailwind's default `fontSize` scale is deliberately NOT overridden. Overriding `lg` from 18px to 20px would silently move type on all 198 files at once with no way to review it. Named utilities let pages migrate deliberately.

- [ ] **Step 1: Add the scale**

```css
  .t-caption  { @apply text-xs font-medium tracking-wide text-ink-500 dark:text-ink-400; }
  .t-body     { @apply text-sm text-ink-700 dark:text-ink-300; }
  .t-body-lg  { @apply text-base text-ink-700 dark:text-ink-300; }
  .t-title    { @apply text-[1.25rem] font-semibold tracking-tight text-ink-900 dark:text-ink-100; }
  .t-heading  { @apply text-[1.5rem] font-semibold tracking-tight text-ink-900 dark:text-ink-100; }
  .t-display  { @apply font-display text-[2rem] font-semibold tracking-tight text-ink-900 dark:text-ink-100; }
```

- [ ] **Step 2: Verify and commit**

Run: `cd frontend && npm run build && npm run lint`

```bash
git add frontend/src/index.css
git commit -m "feat(design): add the six-step type scale utilities"
```

---

## Task 4: Table treatment

**Files:**
- Modify: `frontend/src/index.css` (the `.table-clean` rules near line 304)

**Interfaces:**
- Produces: a `.table-clean` that is correct enough that the 24 hand-rolled tables can adopt it unchanged in Task 6.

- [ ] **Step 1: Restate `.table-clean`**

```css
  .table-clean {
    @apply w-full text-sm text-left border-collapse;
    font-variant-numeric: tabular-nums;
  }
  .table-clean thead th {
    @apply t-caption uppercase bg-ink-50 dark:bg-ink-900/60
           border-b border-ink-200 dark:border-ink-800 px-3 font-semibold;
    height: var(--row-h);
    position: sticky;
    top: 0;
    z-index: 1;
  }
  .table-clean tbody td {
    @apply px-3 border-b border-ink-100 dark:border-ink-800/60
           text-ink-700 dark:text-ink-300 align-middle;
    height: var(--row-h);
  }
  .table-clean tbody tr {
    transition: background-color var(--dur-fast) var(--ease-out);
  }
  .table-clean tbody tr:hover {
    @apply bg-ink-50/70 dark:bg-ink-800/40;
  }
  .table-clean td.num, .table-clean th.num { @apply text-right; }
```

- [ ] **Step 2: Check the 6 existing consumers still look right**

Run: `cd frontend && npm test`
Then start `npm run dev` and view the six files that already use `.table-clean`:
`grep -rl "table-clean" src --include='*.jsx'`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(design): sticky headers, tabular numerals and row hover on .table-clean"
```

---

## Task 5: Loading, error and denied states

**Files:**
- Create: `frontend/src/components/ui/Skeleton.jsx`
- Create: `frontend/src/components/ui/ErrorState.jsx`
- Create: `frontend/src/components/ui/Skeleton.test.jsx`
- Create: `frontend/src/components/ui/ErrorState.test.jsx`
- Modify: `frontend/src/components/EmptyState.jsx`
- Modify: `frontend/src/components/ModuleGuard.jsx`

**Interfaces:**
- Produces:
  - `<Skeleton className />` and `<SkeletonTable rows={number} cols={number} />` from `components/ui/Skeleton.jsx`
  - `<ErrorState title={string} message={string} onRetry={function|undefined} />` from `components/ui/ErrorState.jsx`
- Consumes: `.skeleton` and `.empty` from Task 2.

- [ ] **Step 1: Write the failing test for Skeleton**

`frontend/src/components/ui/Skeleton.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { Skeleton, SkeletonTable } from './Skeleton';

describe('Skeleton', () => {
  it('is hidden from assistive technology', () => {
    render(<Skeleton className="h-4 w-24" />);
    expect(screen.getByTestId('skeleton')).toHaveAttribute('aria-hidden', 'true');
  });

  it('renders the requested grid of cells', () => {
    render(<SkeletonTable rows={3} cols={4} />);
    expect(screen.getAllByTestId('skeleton')).toHaveLength(12);
  });

  it('announces loading once for screen readers', () => {
    render(<SkeletonTable rows={2} cols={2} />);
    expect(screen.getByRole('status')).toHaveTextContent(/loading/i);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd frontend && npm test -- Skeleton`
Expected: FAIL, cannot resolve `./Skeleton`.

- [ ] **Step 3: Implement Skeleton**

```jsx
export function Skeleton({ className = '' }) {
  return <div data-testid="skeleton" aria-hidden="true" className={`skeleton ${className}`} />;
}

export function SkeletonTable({ rows = 5, cols = 4 }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">Loading</span>
      <div className="flex flex-col gap-2">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex gap-2">
            {Array.from({ length: cols }).map((_, c) => (
              <Skeleton key={c} className="h-5 flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run it and watch it pass**

Run: `cd frontend && npm test -- Skeleton`
Expected: PASS, 3 tests.

- [ ] **Step 5: Write the failing test for ErrorState**

`frontend/src/components/ui/ErrorState.test.jsx`:

```jsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import ErrorState from './ErrorState';

describe('ErrorState', () => {
  it('shows the message and calls onRetry', async () => {
    const onRetry = vi.fn();
    render(<ErrorState title="Could not load patients" message="The server did not respond." onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load patients');
    await userEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('omits the retry button when no handler is given', () => {
    render(<ErrorState title="Could not load" message="No access." />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run it and watch it fail, then implement**

Run: `cd frontend && npm test -- ErrorState` (expect FAIL), then:

```jsx
import { AlertTriangle } from 'lucide-react';

export default function ErrorState({ title, message, onRetry }) {
  return (
    <div role="alert" className="empty">
      <AlertTriangle className="h-8 w-8 text-status-critical" aria-hidden="true" />
      <p className="t-title">{title}</p>
      {message ? <p className="t-body max-w-sm">{message}</p> : null}
      {onRetry ? (
        <button type="button" className="btn btn-secondary" onClick={onRetry}>Try again</button>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 7: Run it and watch it pass**

Run: `cd frontend && npm test -- ErrorState`
Expected: PASS, 2 tests.

- [ ] **Step 8: Rework EmptyState and ModuleGuard**

Read both files first. Rework `EmptyState.jsx` to use the `.empty` class and the `.t-title` and `.t-body` scale, keeping its existing props and any `data-testid` untouched. Rework the denial branch of `ModuleGuard.jsx` from its current abrupt output into a designed state: module name, one sentence on why it is unavailable, and the action to take (contact an administrator). Do not change its gating logic.

- [ ] **Step 9: Verify the whole suite, since ModuleGuard is widely rendered**

Run: `cd frontend && npm test && npm run lint`
Expected: all 51 suites plus the 2 new ones pass.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/ui frontend/src/components/EmptyState.jsx frontend/src/components/ModuleGuard.jsx
git commit -m "feat(ui): add Skeleton and ErrorState, redesign EmptyState and ModuleGuard denial"
```

---

## Task 6: Normalise the 24 hand-rolled tables

**Files:**
- Modify: the 24 files that contain `<table` but not `table-clean`. Enumerate them with:
  `cd frontend/src && grep -rl "<table" --include='*.jsx' . | xargs grep -L "table-clean"`

**Interfaces:**
- Consumes: `.table-clean` from Task 4, `SkeletonTable` from Task 5.

- [ ] **Step 1: List the files and work through them one at a time**

For each file: add `className="table-clean"` to the `<table>`, delete the per-file `<thead>` and `<td>` utility classes that `.table-clean` now provides, add `className="num"` to numeric columns, and replace any ad hoc loading text with `<SkeletonTable rows={5} cols={n} />`.

- [ ] **Step 2: Never touch the selectors tests rely on**

Leave every `data-testid`, `aria-label`, caption and column header text exactly as it is. Only class names change.

- [ ] **Step 3: Run the suite after every third file, not at the end**

Run: `cd frontend && npm test`
Expected: green. If a suite fails, it is because a class-bearing element was removed rather than restyled. Restore the element and move its classes instead.

- [ ] **Step 4: Check both themes on three of the converted pages**

Run `npm run dev`, then view Inventory, Cheques and Billing in light and dark.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "refactor(ui): route all tables through .table-clean with tabular numerals"
```

---

## Task 7: Real tabs

**Files:**
- Create: `frontend/src/components/ui/Tabs.jsx`
- Create: `frontend/src/components/ui/Tabs.test.jsx`

**Interfaces:**
- Produces: `<Tabs items={[{ id, label, count? }]} activeId={string} onChange={(id) => void} />`. Renders `role="tablist"` with `role="tab"` children, `aria-selected` on the active tab, and left and right arrow key navigation.

- [ ] **Step 1: Write the failing test**

```jsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import Tabs from './Tabs';

const items = [
  { id: 'orders', label: 'Orders' },
  { id: 'results', label: 'Results', count: 3 },
];

describe('Tabs', () => {
  it('marks the active tab as selected', () => {
    render(<Tabs items={items} activeId="orders" onChange={() => {}} />);
    expect(screen.getByRole('tab', { name: /orders/i })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: /results/i })).toHaveAttribute('aria-selected', 'false');
  });

  it('reports the clicked tab', async () => {
    const onChange = vi.fn();
    render(<Tabs items={items} activeId="orders" onChange={onChange} />);
    await userEvent.click(screen.getByRole('tab', { name: /results/i }));
    expect(onChange).toHaveBeenCalledWith('results');
  });

  it('moves between tabs with the arrow keys', async () => {
    const onChange = vi.fn();
    render(<Tabs items={items} activeId="orders" onChange={onChange} />);
    screen.getByRole('tab', { name: /orders/i }).focus();
    await userEvent.keyboard('{ArrowRight}');
    expect(onChange).toHaveBeenCalledWith('results');
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd frontend && npm test -- Tabs`
Expected: FAIL, cannot resolve `./Tabs`.

- [ ] **Step 3: Implement Tabs**

Underline indicator rather than a pill, animated with `transform` only so it stays interruptible.

```jsx
import { useRef } from 'react';

export default function Tabs({ items, activeId, onChange }) {
  const refs = useRef([]);

  function onKeyDown(event, index) {
    const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    const next = (index + delta + items.length) % items.length;
    refs.current[next]?.focus();
    onChange(items[next].id);
  }

  return (
    <div role="tablist" className="flex items-center gap-1 border-b border-ink-200 dark:border-ink-800">
      {items.map((item, index) => {
        const active = item.id === activeId;
        return (
          <button
            key={item.id}
            ref={(node) => { refs.current[index] = node; }}
            type="button"
            role="tab"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(item.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={`relative inline-flex items-center gap-2 px-3 text-sm font-medium
              ${active ? 'text-brand-700 dark:text-brand-300' : 'text-ink-500 dark:text-ink-400 hover:text-ink-700 dark:hover:text-ink-200'}`}
            style={{ height: 'var(--ctl-h)', transition: 'color var(--dur-fast) var(--ease-out)' }}
          >
            {item.label}
            {typeof item.count === 'number' ? <span className="badge-neutral tnum">{item.count}</span> : null}
            <span
              aria-hidden="true"
              className="absolute inset-x-0 -bottom-px h-0.5 origin-left bg-brand-600"
              style={{
                transform: `scaleX(${active ? 1 : 0})`,
                transition: 'transform var(--dur) var(--ease-out)',
              }}
            />
          </button>
        );
      })}
    </div>
  );
}
```

The indicator animates `scaleX` from 0 to 1 rather than appearing, and never animates the element itself from `scale(0)`, which would make the label pop.

- [ ] **Step 4: Run it and watch it pass**

Run: `cd frontend && npm test -- Tabs`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/Tabs.jsx frontend/src/components/ui/Tabs.test.jsx
git commit -m "feat(ui): add an accessible Tabs component with arrow key navigation"
```

---

## Task 8: App shell and page furniture

**Files:**
- Modify: `frontend/src/components/layouts/MainLayout.jsx`
- Modify: `frontend/src/components/PageHeader.jsx`
- Modify: `frontend/src/components/StatTile.jsx`
- Create: `frontend/src/components/ui/Toolbar.jsx`

**Interfaces:**
- Produces: `<Toolbar left={node} right={node} />`, a sticky filter and action bar using `var(--sec-gap)`.
- Consumes: density tokens from Task 1.

- [ ] **Step 1: Put the workspace on compact density**

In `MainLayout.jsx`, add `density-compact` to the class list of the element that wraps the routed content. This is the single switch that tightens all 25 module pages.

- [ ] **Step 2: Rework the shell chrome**

Sidebar and top bar: cyan reserved for the active nav item only, borders instead of shadows, `var(--dur-fast)` transitions on hover. Keep every route, label and icon.

- [ ] **Step 3: Rework PageHeader and StatTile**

`PageHeader` adopts `.t-heading` for the title and `.t-body` for the description. `StatTile` adopts `.tnum` on its value and drops any shadow in favour of the `.card` border.

- [ ] **Step 4: Add Toolbar and verify the whole app in both themes**

Run: `cd frontend && npm test && npm run lint && npm run build`
Then `npm run dev` and walk five module pages in light and dark.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components
git commit -m "feat(ui): compact workspace density, reworked shell, PageHeader, StatTile and new Toolbar"
```

---

## Tasks 9 to 13: Module page restyle batches

Structure preserved, classes only. For each page in the batch: adopt the type scale, replace ad hoc loading and empty markup with `SkeletonTable`, `EmptyState` and `ErrorState`, adopt `Tabs` where the page hand-rolls tabs, add `.tnum` to every number, confirm dark parity, and confirm no `data-testid` moved.

- [ ] **Task 9:** `Triage.jsx`, `Appointments.jsx`, `QueueBoard.jsx`, `Calendar.jsx`. Run `npm test -- Triage Appointments QueueBoard`, then commit `feat(design): restyle triage, appointments, queue and calendar`.
- [ ] **Task 10:** `Wards.jsx`, `Theatre.jsx`, `Radiology.jsx`, `MedicalHistory.jsx`. Run `npm test`, then commit `feat(design): restyle wards, theatre, radiology and medical history`.
- [ ] **Task 11:** `Inventory.jsx`, `Cheques.jsx`, `Billing.jsx`, `Messages.jsx`. Run `npm test`, then commit `feat(design): restyle inventory, cheques, billing and messages`.
- [ ] **Task 12:** `Dialysis.jsx` plus `pages/dialysis/*` (11 files), which already follow the per-tab convention. Run `npm test -- dialysis`, then commit `feat(design): restyle the dialysis module`.
- [ ] **Task 13:** `Maternity.jsx` plus `pages/maternity/*`, including `PartographChart.jsx`. The partograph is a clinical chart: change only its surrounding chrome, never its plotted scales, gridlines or alert and action lines. Run `npm test -- maternity`, then commit `feat(design): restyle the maternity module`.
- [ ] **Task 13b:** `Profile.jsx`, `Branding.jsx`, `MpesaSettings.jsx`, `Support.jsx`. These four are form-heavy rather than table-heavy, so the work is adopting `.field` for every control, `.t-title` for section headings, and `Toolbar` for their save and cancel rows. `Branding.jsx` (524 lines) also owns `LetterheadStudio`; leave the letterhead preview geometry alone, it is print-calibrated. Run `npm test -- Branding LetterheadStudio`, then commit `feat(design): restyle profile, branding, M-Pesa settings and support`.

---

## Tasks 14 to 18: Layout rework

These seven pages are tab walls in single files. Extract tabs into `pages/<module>/` components following the convention already set by `pages/clinical/` and `pages/dialysis/`. Extraction is a means to make the redesign tractable, never a line count exercise. Behaviour must be identical afterwards.

- [ ] **Task 14: `Accounting.jsx` (3,248 lines).** Extract each tab into `pages/accounting/`, alongside the existing `BudgetingTab.jsx` and `NotesTab.jsx`. Rebuild the ledger views on `.table-clean` with right-aligned `.num` money columns. Run `npm test`, commit `refactor(accounting): extract tabs and rebuild the ledger layout`.
- [ ] **Task 15: `Patients.jsx` (1,962 lines).** Extract the list, detail and registration flows. The list becomes a `Toolbar` plus `.table-clean`. Run `npm test -- Patients`, commit `refactor(patients): extract views and rebuild the patient list layout`.
- [ ] **Task 16: `ClinicalDesk.jsx` (1,360 lines).** Already partly extracted into `pages/clinical/`. Finish the extraction, put the encounter surface on a two column layout at `lg` and above with the patient context sticky. Run `npm test -- clinical ClinicalDesk`, commit `refactor(clinical): finish tab extraction and rebuild the encounter layout`.
- [ ] **Task 17: `Pharmacy.jsx` (1,208 lines) and `Laboratory.jsx` (918 lines).** Extract into `pages/pharmacy/` and `pages/laboratory/`. The dispensing cart and the result entry grid are the two surfaces that need real layout attention. Run `npm test -- Pharmacy Laboratory`, commit `refactor(pharmacy,laboratory): extract tabs and rebuild the dispensing and results layouts`.
- [ ] **Task 18: `Settings.jsx` and `AdminDashboard.jsx`.** Settings becomes a left rail of sections plus a content pane. AdminDashboard rebuilds its grid on `StatTile` with a clear primary metric row. Run `npm test`, commit `refactor(admin): rebuild the settings and admin dashboard layouts`.

---

## Task 19: Marketing surfaces

**Files:** `frontend/src/pages/Landing.jsx`, `Home.jsx`, `Demo.jsx`, `frontend/src/components/PublicFooter.jsx`, `ContactStrip.jsx`, `ContactForm.jsx`

These stay on comfortable density. Keep `WebGLHero` and `PremiumBackground`. `.card-glass` is permitted here and nowhere else. Apply the type scale, fix the spacing rhythm to `var(--sec-gap)` multiples, and keep every SEO element in `Seo.jsx` untouched.

- [ ] Run `cd frontend && npm test && npm run build`, check the hero on a 390px viewport, then commit `feat(design): restyle the marketing surfaces`.

---

## Task 20: Auth and patient portal

**Files:** `Login.jsx`, `ForgotPassword.jsx`, `ResetPassword.jsx`, `ChangePassword.jsx`, `PatientPortal.jsx`, `frontend/src/components/PasswordInput.jsx`

These are pinned light per the dark mode architecture; do not add `dark:` variants. Adopt `.field` for every form control so labels, hints and errors are consistent. Verify the error paths still render their existing messages.

- [ ] Run `cd frontend && npm test && npm run lint`, then commit `feat(design): restyle the auth pages and patient portal`.

---

## Task 21: Superadmin

**Files:** `frontend/src/components/layouts/SuperAdminLayout.jsx` and the `/superadmin` routes

Keeps its own identity per `design-system/medifleet-superadmin/MASTER.md` and its independent `hms_admin_theme` toggle. Adopt the shared primitives (`.card`, `.table-clean`, `Tabs`, `Skeleton`, `ErrorState`) so a fix does not have to be made twice, but do not import the tenant workspace palette.

- [ ] Run `cd frontend && npm test`, then commit `feat(design): adopt shared primitives in the superadmin surfaces`.

---

## Task 22: Em dash sweep and copy pass

**Files:** all of `frontend/src` (1,113 occurrences across 155 files at the time of writing)

- [ ] **Step 1: Enumerate**

Run: `cd frontend/src && grep -rn "—" --include='*.jsx' --include='*.js' --include='*.css' . | wc -l`

- [ ] **Step 2: Rewrite in context, file by file**

Do NOT run a blanket `sed` replacing every em dash with a hyphen; that reads worse than the original. Read each line and choose a colon, a comma, parentheses or a full stop as the sentence requires. Test description strings and code comments count too.

- [ ] **Step 3: Verify none remain and nothing broke**

Run: `cd frontend && ! grep -rq "—" src && npm test && npm run lint`
Expected: the grep finds nothing, all suites pass.

- [ ] **Step 4: Copy clarify pass**

Review button labels, error messages and empty state copy for clarity. Do not change clinical labels, units or factual copy; if one reads wrong, ask rather than edit.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "chore(copy): remove em dashes and clarify labels, errors and empty states"
```

---

## Task 23: Verification and finish

- [ ] **Step 1: Full green**

Run: `cd frontend && npm test && npm run lint && npm run build`
Expected: 51 plus 3 new suites pass, lint clean, build succeeds.

Then run the spec's remaining mechanical gates:

```bash
cd frontend
! grep -rq "—" src                                    # no em dashes
grep -rnE "#[0-9a-fA-F]{6}" src --include='*.jsx' | grep -v "\.test\." # no raw hex in components
grep -rl "<table" src --include='*.jsx' | xargs grep -L "table-clean"  # every table normalised
```

Expected: the first finds nothing, the second returns only deliberate exceptions such as chart and letterhead colour constants, the third returns nothing.

- [ ] **Step 2: Screenshots**

With `npm run dev` running, capture every redesigned route through the Playwright MCP at 1440 and 390 wide, in light and dark. These are the acceptance evidence for the PR.

- [ ] **Step 3: Keyboard and contrast pass**

On the seven reworked pages: tab through every control, confirm a visible focus ring, confirm modals trap and restore focus, confirm no interaction is pointer only, and check text contrast to AA in both themes.

- [ ] **Step 4: Finish review**

Dispatch the `impeccable-finish-reviewer` subagent over the branch diff and fix what it returns, in one batch.

- [ ] **Step 5: Open the PR**

```bash
git push -u origin feat/frontend-redesign
gh pr create --base development --title "feat(design): frontend redesign" --body "..."
```

Note in the PR body that this is frontend only, so the path-filtered `migration-check` does not run and the merge needs the admin route.
