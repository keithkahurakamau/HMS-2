import { useState } from 'react';
import { createCase } from './api';
import { errorText } from './errors';

const PRIORITIES = ['Elective', 'Emergency'];

export default function CaseForm({ patientId = '', onClose, onSaved }) {
  const [form, setForm] = useState({
    patient_id: patientId ? String(patientId) : '',
    procedure_name: '', procedure_code: '', diagnosis: '',
    priority: 'Elective', scheduled_at: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = (e) => {
    e.preventDefault();
    if (!form.patient_id) { setError('Patient ID is required'); return; }
    if (!form.procedure_name.trim()) { setError('Procedure is required'); return; }
    setSaving(true);
    setError('');
    const payload = {
      patient_id: Number(form.patient_id),
      procedure_name: form.procedure_name.trim(),
      priority: form.priority,
    };
    if (form.procedure_code) payload.procedure_code = form.procedure_code;
    if (form.diagnosis) payload.diagnosis = form.diagnosis;
    if (form.scheduled_at) payload.scheduled_at = form.scheduled_at;
    createCase(payload)
      .then((created) => onSaved(created))
      .catch((err) => setError(errorText(err, 'Failed to create case')))
      .finally(() => setSaving(false));
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 backdrop-blur-sm p-4"
         role="dialog" aria-modal="true" aria-label="New surgical case">
      <form onSubmit={submit} className="w-full max-w-lg rounded-2xl bg-white dark:bg-ink-900 p-5 shadow-elevated">
        <h3 className="text-base font-semibold text-ink-900 dark:text-white">New surgical case</h3>
        {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <div className="mt-4 grid grid-cols-2 gap-3">
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Patient ID *
            <input type="number" value={form.patient_id} onChange={set('patient_id')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Priority
            <select value={form.priority} onChange={set('priority')} className="input mt-1 w-full">
              {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label className="col-span-2 block text-sm text-ink-700 dark:text-ink-300">
            Procedure *
            <input type="text" value={form.procedure_name} onChange={set('procedure_name')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Procedure code
            <input type="text" value={form.procedure_code} onChange={set('procedure_code')} className="input mt-1 w-full" />
          </label>
          <label className="block text-sm text-ink-700 dark:text-ink-300">
            Scheduled
            <input type="datetime-local" value={form.scheduled_at} onChange={set('scheduled_at')} className="input mt-1 w-full" />
          </label>
          <label className="col-span-2 block text-sm text-ink-700 dark:text-ink-300">
            Diagnosis
            <input type="text" value={form.diagnosis} onChange={set('diagnosis')} className="input mt-1 w-full" />
          </label>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose}
                  className="rounded-lg border border-ink-200 dark:border-ink-800 px-3 py-1.5 text-sm font-medium text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50">
            Cancel
          </button>
          <button type="submit" disabled={saving}
                  className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
            {saving ? 'Saving…' : 'Create case'}
          </button>
        </div>
      </form>
    </div>
  );
}
