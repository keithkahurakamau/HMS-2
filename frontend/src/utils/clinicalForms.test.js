import { describe, it, expect } from 'vitest';
import { computeBmi, serializeAssessPlan, parseAssessPlan, blankMed } from './clinicalForms';

describe('computeBmi', () => {
    it('computes BMI from kg and cm', () => {
        expect(computeBmi('70', '170')).toBe('24.2');
    });
    it('returns null when incomplete', () => {
        expect(computeBmi('', '170')).toBeNull();
        expect(computeBmi('70', '')).toBeNull();
    });
});

describe('assess/plan serialization', () => {
    it('round-trips through serialize + parse', () => {
        const s = serializeAssessPlan({ assessment: 'Stable', plan: 'Review in 2 weeks' });
        expect(s).toBe('Assessment:\nStable\n\nPlan:\nReview in 2 weeks');
        expect(parseAssessPlan(s)).toEqual({ assessment: 'Stable', plan: 'Review in 2 weeks' });
    });
    it('serializes empty to empty string', () => {
        expect(serializeAssessPlan({ assessment: '', plan: '' })).toBe('');
    });
    it('treats an unstructured legacy value as the assessment', () => {
        expect(parseAssessPlan('some old note')).toEqual({ assessment: 'some old note', plan: '' });
    });
});

describe('blankMed', () => {
    it('creates a fresh empty medication row with a uid', () => {
        const m = blankMed();
        expect(m).toMatchObject({ drug: '', formulation: 'Tablet' });
        expect(m._uid).toBeTruthy();
    });
});
