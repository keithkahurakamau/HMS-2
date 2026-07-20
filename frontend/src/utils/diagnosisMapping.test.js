import { describe, it, expect } from 'vitest';
import { buildDiagnosisFields } from './diagnosisMapping';

const T2DM = { code: 'E11.9', description: 'Type 2 diabetes mellitus without complications' };
const HTN = { code: 'I10', description: 'Essential (primary) hypertension' };
const CUSTOM = { code: null, description: 'birth trauma follow-up', custom: true };

describe('buildDiagnosisFields', () => {
    it('joins catalogue codes into icd10_code and falls back descriptions into diagnosis', () => {
        expect(buildDiagnosisFields([T2DM, HTN], '')).toEqual({
            icd10_code: 'E11.9, I10',
            diagnosis: 'Type 2 diabetes mellitus without complications; Essential (primary) hypertension',
        });
    });

    it('keeps custom entries out of icd10_code and puts them in diagnosis', () => {
        expect(buildDiagnosisFields([T2DM, CUSTOM], '')).toEqual({
            icd10_code: 'E11.9',
            diagnosis: 'birth trauma follow-up',
        });
    });

    it('appends the free-text field after custom entries', () => {
        expect(buildDiagnosisFields([CUSTOM], 'clinically stable')).toEqual({
            icd10_code: '',
            diagnosis: 'birth trauma follow-up; clinically stable',
        });
    });

    it('free text alone wins over the catalogue-description fallback', () => {
        expect(buildDiagnosisFields([T2DM], 'working impression')).toEqual({
            icd10_code: 'E11.9',
            diagnosis: 'working impression',
        });
    });

    it('returns empty fields when nothing is recorded', () => {
        expect(buildDiagnosisFields([], '   ')).toEqual({ icd10_code: '', diagnosis: '' });
    });
});
