// Single source of truth for the in-app "What's New" feed. Newest first.
// Bump APP_VERSION and prepend a RELEASES entry whenever we ship user-facing
// changes; users behind this version get the announcement on next load.
export const APP_VERSION = '1.0.0';

export const RELEASES = [
    {
        version: '1.0.0',
        date: '2026-06-24',
        title: 'Clinical flow improvements',
        changes: [
            'Triage can now route patients to any module (lab, pharmacy, radiology, wards, reception).',
            'Doctors now see Random Blood Sugar (RBS) and BMI carried from triage.',
            'Patients can be cancelled when not seen; dashboards show only active patients.',
            'Full triage history now appears in the patient chart, with a "clear previous visit" action.',
        ],
        offerTour: true, // show a "Take the tour" button
    },
];

const KEY = (userId) => `hms_last_seen_version_${userId ?? 'anon'}`;

export function readLastSeenVersion(userId) {
    try { return localStorage.getItem(KEY(userId)); } catch { return null; }
}

export function writeLastSeenVersion(userId, version) {
    try { localStorage.setItem(KEY(userId), version); } catch { /* ignore */ }
}

// Simple semver-ish compare: returns true if `a` > `b`.
export function isNewer(a, b) {
    if (!b) return true;
    const pa = String(a).split('.').map(Number);
    const pb = String(b).split('.').map(Number);
    for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
        const da = pa[i] || 0, db = pb[i] || 0;
        if (da !== db) return da > db;
    }
    return false;
}

// Releases the user hasn't seen yet (strictly newer than lastSeen).
export function unseenReleases(lastSeen) {
    return RELEASES.filter((r) => isNewer(r.version, lastSeen));
}
