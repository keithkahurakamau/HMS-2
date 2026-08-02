// Pure helpers shared by the DoctorV2 clinical-desk form modals. Kept out of the
// component files so Fast Refresh stays happy (only-export-components) and the
// logic is unit-testable on its own.

export const FORMULATIONS = ['Tablet', 'Capsule', 'Syrup', 'Suspension', 'Injection', 'Cream / Ointment', 'Drops', 'Inhaler', 'Suppository', 'Other'];
export const FREQUENCIES = ['OD (once daily)', 'BD (twice daily)', 'TDS (three times daily)', 'QDS (four times daily)', 'PRN (as needed)', 'STAT (immediately)', 'Nocte (at night)'];
export const blankMed = () => ({ _uid: crypto.randomUUID(), drug: '', formulation: 'Tablet', dosage: '', frequency: '', duration: '' });

export const computeBmi = (weight, height) => {
    const w = parseFloat(weight);
    const h = parseFloat(height) / 100;
    if (!w || !h) return null;
    return (w / (h * h)).toFixed(1);
};

// assessment_plan is stored as one string. Keep a stable, round-trippable
// serialization so re-opening the editor splits it back into the two fields.
export const serializeAssessPlan = ({ assessment, plan }) => {
    const a = (assessment || '').trim();
    const p = (plan || '').trim();
    if (!a && !p) return '';
    return `Assessment:\n${a}\n\nPlan:\n${p}`;
};

export const parseAssessPlan = (value) => {
    if (!value) return { assessment: '', plan: '' };
    const m = value.match(/^Assessment:\n([\s\S]*?)\n\nPlan:\n([\s\S]*)$/);
    if (m) return { assessment: m[1].trim(), plan: m[2].trim() };
    return { assessment: value.trim(), plan: '' };
};
