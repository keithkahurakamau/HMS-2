import React, { useState } from 'react';
import { Sparkles, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useJourney } from '../context/JourneyContext';
import { APP_VERSION, unseenReleases, writeLastSeenVersion, readLastSeenVersion } from '../releases';

/**
 * WhatsNew — shows a versioned "what changed" panel when the signed-in user is
 * behind the current APP_VERSION. Dismissing records APP_VERSION as last-seen
 * (per-user, localStorage) so it won't reappear. Optional "Take the tour"
 * button replays the product tours via JourneyContext.
 */
export default function WhatsNew() {
    const { user } = useAuth();
    const { restartAll } = useJourney();
    const userId = user?.user_id ?? null;

    // Compute unseen releases once on mount (userId is stable after login).
    // Using lazy-init avoids calling setState inside an effect.
    const [items] = useState(() =>
        userId ? unseenReleases(readLastSeenVersion(userId)) : []
    );
    const [open, setOpen] = useState(() => items.length > 0);

    const dismiss = () => {
        writeLastSeenVersion(userId, APP_VERSION);
        setOpen(false);
    };

    const takeTour = () => {
        restartAll();
        dismiss();
    };

    if (!open || items.length === 0) return null;

    const offerTour = items.some((r) => r.offerTour);

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-ink-900/40 p-4" role="dialog" aria-modal="true" aria-label="What's new">
            <div className="card w-full max-w-md p-5">
                <div className="flex items-center justify-between mb-3">
                    <h2 className="font-semibold text-ink-900 dark:text-white flex items-center gap-2">
                        <Sparkles size={18} className="text-brand-600" /> What&apos;s new
                    </h2>
                    <button type="button" onClick={dismiss} aria-label="Close" className="text-ink-400 hover:text-ink-700">
                        <X size={18} />
                    </button>
                </div>
                <div className="space-y-4 max-h-[60vh] overflow-y-auto">
                    {items.map((r) => (
                        <div key={r.version}>
                            <p className="text-sm font-semibold text-ink-800 dark:text-ink-200">
                                v{r.version} · {r.title}
                                <span className="text-xs font-normal text-ink-400 ml-2">{r.date}</span>
                            </p>
                            <ul className="mt-1 list-disc pl-5 space-y-1">
                                {r.changes.map((c) => (
                                    <li key={c} className="text-sm text-ink-600 dark:text-ink-400">{c}</li>
                                ))}
                            </ul>
                        </div>
                    ))}
                </div>
                <div className="mt-5 flex items-center justify-end gap-2">
                    {offerTour && (
                        <button type="button" onClick={takeTour} className="btn-secondary">Take the tour</button>
                    )}
                    <button type="button" onClick={dismiss} className="btn-primary">Got it</button>
                </div>
            </div>
        </div>
    );
}
