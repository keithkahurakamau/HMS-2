import { useState } from 'react';
import { createOrder } from './api';
import { errorText } from './errors';

// key, label, [step] — number inputs; Number()'d and omitted when blank.
const RX = [
  ['dialyzer', 'Dialyzer'], ['membrane_type', 'Membrane'], ['priming', 'Priming'],
  ['k_bath', 'K+ bath'], ['dialysate_calcium', 'Dialysate Ca'],
  ['dialysate_bicarbonate', 'Dialysate HCO₃'], ['dialysate_sodium', 'Dialysate Na'],
];
const RX_NUM = [
  ['dialysate_temp_c', 'Dialysate temp (°C)', '0.1'],
  ['blood_flow_target', 'Blood flow (mL/min)'], ['dialysate_flow_target', 'Dialysate flow (mL/min)'],
  ['treatment_time_min', 'Treatment time (min)'],
];
const FLUID_NUM = [
  ['pre_weight_kg', 'Pre-weight (kg)', '0.1'], ['dry_weight_kg', 'Dry weight (kg)', '0.1'],
  ['target_uf_ml', 'Target UF (mL)'], ['intake_ml', 'Intake (mL)'],
  ['fluid_removal_goal_ml', 'Fluid removal goal (mL)'],
];
const ANTICOAG = ['', 'Heparin', 'Heparin-free', 'LMWH'];

const NUMERIC_KEYS = new Set([...RX_NUM, ...FLUID_NUM].map(([k]) => k));
const TEXT_KEYS = [
  ...RX.map(([k]) => k), 'hiv_hbv_status', 'blood_group',
  'anticoag_type', 'heparin_loading_dose', 'heparin_maintenance_dose', 'heparin_stop_time',
];

function Card({ title, children }) {
  return (
    <fieldset className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4">
      <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-ink-500 dark:text-ink-400">{title}</legend>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{children}</div>
    </fieldset>
  );
}

function Field({ label, value, onChange, type = 'text', step, children }) {
  return (
    <label className="block text-sm text-ink-700 dark:text-ink-300">
      {label}
      {children || (
        <input type={type} step={step} value={value} onChange={onChange} className="input mt-1 w-full" />
      )}
    </label>
  );
}

export default function OrderForm({ patientId = '', onClose, onSaved }) {
  const [form, setForm] = useState({
    patient_id: patientId ? String(patientId) : '',
    dialyzer: '', membrane_type: '', priming: '', k_bath: '',
    dialysate_calcium: '', dialysate_bicarbonate: '', dialysate_sodium: '',
    dialysate_temp_c: '', blood_flow_target: '', dialysate_flow_target: '', treatment_time_min: '',
    anticoag_type: '', heparin_loading_dose: '', heparin_maintenance_dose: '', heparin_stop_time: '',
    pre_weight_kg: '', dry_weight_kg: '', target_uf_ml: '', intake_ml: '', fluid_removal_goal_ml: '',
    hiv_hbv_status: '', blood_group: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.patient_id) { setError('Patient ID is required'); return; }
    setSaving(true);
    setError('');
    const payload = { patient_id: Number(form.patient_id) };
    for (const k of NUMERIC_KEYS) if (form[k] !== '') payload[k] = Number(form[k]);
    for (const k of TEXT_KEYS) if (form[k]) payload[k] = form[k];
    try {
      const created = await createOrder(payload);
      onSaved(created);
    } catch (err) {
      setError(errorText(err, 'Failed to create dialysis order'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 backdrop-blur-sm p-4"
         role="dialog" aria-modal="true" aria-label="New dialysis session">
      <form onSubmit={submit} className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white dark:bg-ink-900 p-5 shadow-elevated">
        <h3 className="text-base font-semibold text-ink-900 dark:text-white">New dialysis session</h3>
        {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Field label="Patient ID *" type="number" value={form.patient_id} onChange={set('patient_id')} />
          <Field label="HIV/HBV status" value={form.hiv_hbv_status} onChange={set('hiv_hbv_status')} />
          <Field label="Blood group" value={form.blood_group} onChange={set('blood_group')} />
        </div>

        <div className="mt-4 space-y-4">
          <Card title="Renal prescription">
            {RX.map(([k, label]) => <Field key={k} label={label} value={form[k]} onChange={set(k)} />)}
            {RX_NUM.map(([k, label, step]) => <Field key={k} label={label} type="number" step={step} value={form[k]} onChange={set(k)} />)}
          </Card>

          <Card title="Anticoagulation">
            <Field label="Type" value={form.anticoag_type} onChange={set('anticoag_type')}>
              <select value={form.anticoag_type} onChange={set('anticoag_type')} className="input mt-1 w-full">
                {ANTICOAG.map((o) => <option key={o} value={o}>{o || '—'}</option>)}
              </select>
            </Field>
            <Field label="Loading dose" value={form.heparin_loading_dose} onChange={set('heparin_loading_dose')} />
            <Field label="Maintenance dose" value={form.heparin_maintenance_dose} onChange={set('heparin_maintenance_dose')} />
            <Field label="Stop time" value={form.heparin_stop_time} onChange={set('heparin_stop_time')} />
          </Card>

          <Card title="Fluid targets">
            {FLUID_NUM.map(([k, label, step]) => <Field key={k} label={label} type="number" step={step} value={form[k]} onChange={set(k)} />)}
          </Card>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose}
                  className="rounded-lg border border-ink-200 dark:border-ink-800 px-3 py-1.5 text-sm font-medium text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50">
            Cancel
          </button>
          <button type="submit" disabled={saving}
                  className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
            {saving ? 'Saving…' : 'Create session'}
          </button>
        </div>
      </form>
    </div>
  );
}
