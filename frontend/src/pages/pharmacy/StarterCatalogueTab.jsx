import React, { useEffect, useMemo, useState } from 'react';
import { Search, PackagePlus, CheckSquare, Square, Sparkles } from 'lucide-react';
import toast from 'react-hot-toast';
import { apiClient } from '../../api/client';
import { SkeletonTable } from '../../components/ui/Skeleton';

// The "adopt starter catalogue" tab: shown on the Pharmacy page only when
// the operator has switched the `pharmacy_starter_catalogue` feature flag
// on for this hospital (Pharmacy.jsx decides that and only mounts this
// component when it's true).
//
// Two independent "not available" states, both clean and non-crashing:
//   - the operator hasn't loaded a real catalogue into the repo CSV yet
//     (available: false from the API)
//   - the request itself fails (network error, unexpected 5xx)
// Neither should ever surface a blank page or an unhandled exception.
export default function StarterCatalogueTab({ canManage }) {
    const [isLoading, setIsLoading] = useState(true);
    const [available, setAvailable] = useState(true);
    const [products, setProducts] = useState([]);
    const [search, setSearch] = useState('');
    const [selected, setSelected] = useState(() => new Set());
    const [isAdopting, setIsAdopting] = useState(false);

    useEffect(() => {
        let cancelled = false;
        setIsLoading(true);
        apiClient.get('/pharmacy/starter-catalogue')
            .then((res) => {
                if (cancelled) return;
                setAvailable(!!res.data?.available);
                setProducts(res.data?.products || []);
            })
            .catch(() => {
                if (cancelled) return;
                // A failed fetch collapses to the same "not available" state
                // shown for an empty catalogue: the hospital doesn't need to
                // know why, and nothing here should crash the Pharmacy page.
                setAvailable(false);
                setProducts([]);
            })
            .finally(() => { if (!cancelled) setIsLoading(false); });
        return () => { cancelled = true; };
    }, []);

    const filtered = useMemo(() => {
        const needle = search.trim().toLowerCase();
        if (!needle) return products;
        return products.filter((name) => name.toLowerCase().includes(needle));
    }, [products, search]);

    const toggleOne = (name) => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(name)) next.delete(name); else next.add(name);
            return next;
        });
    };

    const allFilteredSelected = filtered.length > 0 && filtered.every((n) => selected.has(n));
    const toggleAllFiltered = () => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (allFilteredSelected) {
                filtered.forEach((n) => next.delete(n));
            } else {
                filtered.forEach((n) => next.add(n));
            }
            return next;
        });
    };

    const adopt = async (names) => {
        setIsAdopting(true);
        try {
            const res = await apiClient.post('/pharmacy/starter-catalogue/adopt', { names: names || undefined });
            const { created = 0, skipped = 0 } = res.data || {};
            if (created === 0 && skipped === 0) {
                toast('Nothing selected to adopt.');
            } else if (created === 0) {
                toast(`Already in your inventory: ${skipped} item(s) skipped, nothing new added.`);
            } else {
                toast.success(
                    skipped > 0
                        ? `Added ${created} item(s) to your inventory. ${skipped} already existed and were left as-is.`
                        : `Added ${created} item(s) to your inventory.`
                );
            }
            setSelected(new Set());
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Could not adopt the starter catalogue.');
        } finally {
            setIsAdopting(false);
        }
    };

    if (isLoading) {
        return <div className="card p-6"><SkeletonTable rows={5} cols={2} label="Loading starter catalogue" /></div>;
    }

    if (!available) {
        return (
            <div className="card p-8 text-center">
                <Sparkles size={28} className="mx-auto text-ink-300 dark:text-ink-600 mb-3" aria-hidden="true" />
                <h3 className="text-sm font-semibold text-ink-900 dark:text-white">Starter catalogue not loaded yet</h3>
                <p className="text-xs text-ink-500 dark:text-ink-400 mt-1 max-w-md mx-auto">
                    MediFleet has not loaded a ready-made pharmacy product list for your hospital yet. Once it has,
                    you will be able to browse it here and adopt items straight into your inventory.
                </p>
            </div>
        );
    }

    return (
        <div className="card flex flex-col overflow-hidden">
            <div className="p-4 border-b border-ink-200 dark:border-ink-800 flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
                <div>
                    <h3 className="text-sm font-semibold text-ink-900 dark:text-white">Starter pharmacy catalogue</h3>
                    <p className="text-xs text-ink-500 dark:text-ink-400 mt-0.5">
                        Adopt products into your inventory with quantity 0 and no price set. You price and stock
                        each one yourself afterwards. Adopting again never overwrites an item you have already priced.
                    </p>
                </div>
                {canManage && (
                    <div className="flex gap-2 shrink-0">
                        <button
                            type="button"
                            disabled={isAdopting || selected.size === 0}
                            onClick={() => adopt(Array.from(selected))}
                            className="btn-secondary cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <PackagePlus size={15} /> Adopt selected ({selected.size})
                        </button>
                        <button
                            type="button"
                            disabled={isAdopting || products.length === 0}
                            onClick={() => adopt(null)}
                            className="btn-primary cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                            <PackagePlus size={15} /> Adopt all ({products.length})
                        </button>
                    </div>
                )}
            </div>

            <div className="p-4 border-b border-ink-200 dark:border-ink-800">
                <div className="relative max-w-sm">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" aria-hidden="true" />
                    <label htmlFor="starter-catalogue-search" className="sr-only">Search starter catalogue</label>
                    <input
                        id="starter-catalogue-search"
                        type="search"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search products..."
                        className="w-full bg-white dark:bg-ink-900 border border-ink-200 dark:border-ink-800 rounded-lg pl-8 pr-3 py-2 text-sm text-ink-900 dark:text-white placeholder-ink-400 dark:placeholder-ink-500 focus:outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
                    />
                </div>
            </div>

            <div className="max-h-[28rem] overflow-y-auto custom-scrollbar divide-y divide-ink-100 dark:divide-ink-800">
                {canManage && filtered.length > 0 && (
                    <button
                        type="button"
                        onClick={toggleAllFiltered}
                        className="w-full flex items-center gap-2 px-4 py-2 text-xs font-semibold text-ink-500 dark:text-ink-400 hover:bg-ink-50 dark:hover:bg-ink-800/40 cursor-pointer"
                    >
                        {allFilteredSelected ? <CheckSquare size={14} /> : <Square size={14} />}
                        {allFilteredSelected ? 'Clear selection' : `Select all shown (${filtered.length})`}
                    </button>
                )}
                {filtered.length === 0 && (
                    <p className="text-xs text-ink-500 dark:text-ink-400 italic text-center py-8">
                        No products match "{search}".
                    </p>
                )}
                {filtered.map((name) => (
                    <label
                        key={name}
                        htmlFor={`starter-item-${name}`}
                        className="flex items-center gap-3 px-4 py-2.5 hover:bg-ink-50 dark:hover:bg-ink-800/30 cursor-pointer"
                    >
                        <input
                            id={`starter-item-${name}`}
                            type="checkbox"
                            checked={selected.has(name)}
                            disabled={!canManage}
                            onChange={() => toggleOne(name)}
                            className="size-4 rounded border-ink-300 dark:border-ink-700 text-brand-600 focus:ring-brand-500"
                        />
                        <span className="text-sm text-ink-800 dark:text-ink-100">{name}</span>
                    </label>
                ))}
            </div>
        </div>
    );
}
