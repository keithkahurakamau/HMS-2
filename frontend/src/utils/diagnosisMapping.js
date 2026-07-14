/**
 * Maps the Clinical Desk diagnosis chips + free-text field onto the two
 * MedicalRecord columns.
 *
 * `icd10_code` must only ever hold real catalogue codes (comma-joined):
 * clinical_history.py treats the column as a code list only when every
 * comma-split part looks like a code, so free text there would mangle
 * real codes in visit history. Custom entries and the free-text field go
 * to `diagnosis`; when both are empty we fall back to the catalogue
 * descriptions so the visit-history summary line still reads naturally.
 */
export function buildDiagnosisFields(chips, freeText) {
    const catalogue = chips.filter((c) => !c.custom && c.code);
    const custom = chips.filter((c) => c.custom);
    const text = (freeText || '').trim();
    const parts = [...custom.map((c) => c.description), ...(text ? [text] : [])];
    return {
        icd10_code: catalogue.map((c) => c.code).join(', '),
        diagnosis: parts.length ? parts.join('; ') : catalogue.map((c) => c.description).join('; '),
    };
}
