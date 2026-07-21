// Re-hydrates the Clinical Desk form from a resumable (Draft/Returned)
// medical record returned by GET /clinical/patients/{id}/resumable.

// Split a stored "; "-joined string back into discrete entries. Newer
// records join with "; "; older free-text ones become a single entry.
export const splitComplaints = (s) => (s || '')
    .split(/\s*;\s*|\n+/)
    .flatMap((c) => { const t = c.trim(); return t ? [t] : []; });

// Structured prescriptions serialise as a JSON array in treatment_plan.
// Legacy free-text plans have no structured rows to rebuild — they parse
// to [] and the doctor re-enters medications if still needed.
const parseMedications = (treatmentPlan) => {
    if (!treatmentPlan) return [];
    let parsed;
    try {
        parsed = JSON.parse(treatmentPlan);
    } catch {
        return [];
    }
    if (!Array.isArray(parsed)) return [];
    return parsed
        .filter((m) => m && typeof m === 'object' && (m.drug || '').trim())
        .map((m) => ({
            _uid: crypto.randomUUID(),
            drug: m.drug || '',
            formulation: m.formulation || 'Tablet',
            dosage: m.dosage || '',
            frequency: m.frequency || '',
            duration: m.duration || '',
        }));
};

/**
 * Maps a resumable record onto the Clinical Desk's form-state shape.
 * Vitals fall back to '' (the inputs are controlled); lists to [].
 */
export function recordToFormState(record) {
    const icdCodes = record.icd10_codes || [];
    // buildDiagnosisFields writes the joined catalogue descriptions into
    // `diagnosis` as a fallback when no custom text was entered; on resume
    // that text is already represented by the rebuilt chips, so don't
    // duplicate it into the free-text field.
    const descriptionFallback = icdCodes.map((c) => c.description).join('; ');
    const diagnosisText = record.diagnosis === descriptionFallback ? '' : (record.diagnosis || '');
    return {
        vitals: {
            weight: record.weight_kg ?? '',
            height: record.height_cm ?? '',
            bp: record.blood_pressure ?? '',
            hr: record.heart_rate ?? '',
            rr: record.respiratory_rate ?? '',
            temp: record.temperature ?? '',
            spo2: record.spo2 ?? '',
            glucose: record.blood_glucose ?? '',
        },
        complaints: splitComplaints(record.chief_complaint),
        physicalExams: splitComplaints(record.physical_examination),
        hpi: record.history_of_present_illness || '',
        diagnosisText,
        internalNotes: record.internal_notes || '',
        icdCodes,
        medications: parseMedications(record.treatment_plan),
    };
}
