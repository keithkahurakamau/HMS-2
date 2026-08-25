import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Guard: every printout must go through printDocument().
 *
 * Tenant letterhead, house styles and the CSP-safe blob popup all live in
 * printDocument.js. A feature that calls window.print() or writes its own
 * document silently opts out of all three — which is exactly how the pharmacy
 * receipt, the sick note and the partograph ended up printing without the
 * hospital's letterhead after it was uploaded.
 *
 * This test fails on the next one, at authoring time rather than in a clinic.
 */

const SRC = dirname(dirname(fileURLToPath(import.meta.url)));  // …/src

// printDocument.js legitimately owns the popup/iframe printing primitives.
const ALLOWED = new Set(['utils/printDocument.js']);

const collect = (dir, out = []) => {
    for (const name of readdirSync(dir)) {
        const full = join(dir, name);
        if (statSync(full).isDirectory()) {
            collect(full, out);
        } else if (/\.(js|jsx)$/.test(name) && !/\.test\.(js|jsx)$/.test(name)) {
            out.push(full);
        }
    }
    return out;
};

// Match real calls, not the word inside a comment or a string of prose.
const DIRECT_PRINT = /(?<!\/\/.*)\bwindow\.print\s*\(/;
const DOC_WRITE = /(?<!\/\/.*)\bdocument\.write\s*\(/;

const offenders = (pattern) =>
    collect(SRC)
        .map((file) => ({ rel: relative(SRC, file), src: readFileSync(file, 'utf8') }))
        .filter(({ rel }) => !ALLOWED.has(rel))
        .filter(({ src }) =>
            src.split('\n').some((line) => !line.trim().startsWith('//') && pattern.test(line)))
        .map(({ rel }) => rel);

describe('print coverage', () => {
    it('has no window.print() outside the shared print engine', () => {
        expect(offenders(DIRECT_PRINT)).toEqual([]);
    });

    it('has no document.write() building a rival print document', () => {
        expect(offenders(DOC_WRITE)).toEqual([]);
    });

    it('still finds source files to scan', () => {
        // Guards the guard: a broken glob would make the checks vacuously pass.
        expect(collect(SRC).length).toBeGreaterThan(50);
    });
});
