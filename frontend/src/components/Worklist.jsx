import React, { useMemo, useState } from 'react';
import { Search, Plus, Inbox } from 'lucide-react';

/**
 * Worklist — the shared master/detail worklist used by the Theatre and Dialysis
 * modules (and anything else with "a filterable list of things on the left, the
 * selected thing's board on the right").
 *
 * It owns the ergonomics so every module gets the same UX for free:
 *   • instant client-side search (patient / procedure / whatever `searchText` returns),
 *   • one-click status filter chips with live counts (no hunting in a dropdown),
 *   • a scrollable list with a clear selected state,
 *   • friendly empty states for both the list and the detail pane.
 *
 * The parent still owns loading the rows and rendering the detail (`children`);
 * pass ALL rows in (unfiltered) so the chip counts and search work client-side.
 *
 * Props:
 *   items          array   all rows (unfiltered)
 *   statuses       array   status values in display order (e.g. ['Scheduled','Completed'])
 *   statusLabels   object? pretty labels, e.g. { InTheatre: 'In theatre' }
 *   chipClass      object  status -> tailwind classes for the row/chip pill
 *   getKey         fn(row) -> stable key
 *   getStatus      fn(row) -> status string
 *   primary        fn(row) -> primary line (patient)
 *   secondary      fn(row) -> secondary line (procedure / treatment)
 *   meta           fn(row)? -> optional right-aligned meta (time, priority node)
 *   searchText     fn(row) -> string searched against the query
 *   selectedKey    the currently-open row's key
 *   onSelect       fn(row)
 *   onNew          fn()
 *   newLabel       string
 *   searchPlaceholder string
 *   emptyTitle     string  shown when there are no rows at all
 *   emptyHint      string? sub-line under emptyTitle
 *   error          string?
 *   children       the detail pane (board or its own empty state)
 */
export default function Worklist({
  items = [],
  statuses = [],
  statusLabels = {},
  chipClass = {},
  getKey,
  getStatus,
  primary,
  secondary,
  meta,
  searchText,
  selectedKey,
  onSelect,
  onNew,
  newLabel = 'New',
  searchPlaceholder = 'Search…',
  emptyTitle = 'Nothing here yet.',
  emptyHint,
  error,
  children,
}) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(''); // '' = All

  const counts = useMemo(() => {
    const c = {};
    for (const it of items) {
      const s = getStatus(it);
      c[s] = (c[s] || 0) + 1;
    }
    return c;
  }, [items, getStatus]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((it) => {
      if (active && getStatus(it) !== active) return false;
      if (q && !String(searchText(it) || '').toLowerCase().includes(q)) return false;
      return true;
    });
  }, [items, query, active, getStatus, searchText]);

  const labelFor = (s) => statusLabels[s] || s;

  const chip = (value, label, count) => {
    const on = active === value;
    return (
      <button
        key={value || 'all'}
        type="button"
        aria-pressed={on}
        onClick={() => setActive(value)}
        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
          on
            ? 'bg-brand-600 text-white shadow-soft'
            : 'bg-ink-100 text-ink-600 hover:bg-ink-200 dark:bg-ink-800 dark:text-ink-300 dark:hover:bg-ink-700'
        }`}
      >
        {label}
        <span className={`tabular-nums ${on ? 'text-white/80' : 'text-ink-400 dark:text-ink-500'}`}>{count}</span>
      </button>
    );
  };

  return (
    <div>
      {/* Search + primary action */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-1">
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={searchPlaceholder}
            aria-label={searchPlaceholder}
            className="input pl-9"
          />
        </div>
        {onNew && (
          <button type="button" onClick={onNew} className="btn-primary shrink-0">
            <Plus size={15} /> {newLabel}
          </button>
        )}
      </div>

      {/* Status filter chips with live counts */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {chip('', 'All', items.length)}
        {statuses.map((s) => chip(s, labelFor(s), counts[s] || 0))}
      </div>

      {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,22rem)_1fr]">
        {/* Master list */}
        <div className="card-flush overflow-hidden">
          {items.length === 0 ? (
            <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
              <Inbox size={28} className="text-ink-300 dark:text-ink-600" strokeWidth={1.5} />
              <p className="text-sm font-medium text-ink-600 dark:text-ink-300">{emptyTitle}</p>
              {emptyHint && <p className="text-xs text-ink-500 dark:text-ink-400">{emptyHint}</p>}
            </div>
          ) : filtered.length === 0 ? (
            <p className="px-6 py-10 text-center text-sm text-ink-500 dark:text-ink-400">No matches for the current filters.</p>
          ) : (
            <ul className="max-h-[60vh] divide-y divide-ink-100 overflow-y-auto custom-scrollbar dark:divide-ink-800">
              {filtered.map((it) => {
                const key = getKey(it);
                const s = getStatus(it);
                const on = selectedKey === key;
                return (
                  <li key={key}>
                    <button
                      type="button"
                      onClick={() => onSelect(it)}
                      className={`flex w-full items-center justify-between gap-2 px-4 py-3 text-left transition-colors ${
                        on
                          ? 'bg-brand-50 dark:bg-brand-500/15'
                          : 'hover:bg-ink-50 dark:hover:bg-ink-800/40'
                      }`}
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-ink-900 dark:text-white">{primary(it)}</span>
                        <span className="block truncate text-xs text-ink-500 dark:text-ink-400">{secondary(it)}</span>
                      </span>
                      <span className="flex shrink-0 flex-col items-end gap-1">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${chipClass[s] || 'bg-ink-100 text-ink-600 dark:bg-ink-800 dark:text-ink-300'}`}>{labelFor(s)}</span>
                        {meta && <span className="text-2xs text-ink-400 dark:text-ink-500">{meta(it)}</span>}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Detail pane */}
        <div className="card-flush p-4">{children}</div>
      </div>
    </div>
  );
}
