import { useState } from 'react';
import { addTeamMember, removeTeamMember, addConsumable, addRecoveryObs, getCase } from './api';
import { errorText } from './errors';

const ROLES = ['Surgeon', 'Assistant', 'Anaesthetist', 'Scrub-Nurse', 'Circulating-Nurse', 'Perfusionist'];

// Team, consumables/implants and post-op recovery panels for a case. Split out
// of CaseBoard to keep each component focused.
export default function CaseExtras({ caseObj, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [team, setTeam] = useState({ role: 'Surgeon', name: '' });
  const [cons, setCons] = useState({ item_name: '', qty: '', is_implant: false, serial_no: '' });
  const [obs, setObs] = useState({ bp_systolic: '', bp_diastolic: '', pulse: '', spo2: '', pain_score: '', consciousness: 'A' });

  const inRecovery = caseObj.status === 'Recovery' || caseObj.status === 'Completed';
  const isTerminal = caseObj.status === 'Completed' || caseObj.status === 'Cancelled';

  const run = (fn) => {
    setBusy(true);
    setError('');
    return fn()
      .then(() => getCase(caseObj.case_id))
      .then(onChanged)
      .catch((err) => setError(errorText(err, 'Action failed')))
      .finally(() => setBusy(false));
  };

  const submitTeam = (e) => {
    e.preventDefault();
    run(() => addTeamMember(caseObj.case_id, { role: team.role, name: team.name || undefined }))
      .then(() => setTeam({ role: 'Surgeon', name: '' }));
  };
  const submitCons = (e) => {
    e.preventDefault();
    if (!cons.item_name.trim()) return;
    run(() => addConsumable(caseObj.case_id, {
      item_name: cons.item_name.trim(), qty: cons.qty !== '' ? Number(cons.qty) : undefined,
      is_implant: cons.is_implant, serial_no: cons.serial_no || undefined,
    })).then(() => setCons({ item_name: '', qty: '', is_implant: false, serial_no: '' }));
  };
  const submitObs = (e) => {
    e.preventDefault();
    const payload = {};
    for (const k of ['bp_systolic', 'bp_diastolic', 'pulse', 'spo2', 'pain_score']) {
      if (obs[k] !== '') payload[k] = Number(obs[k]);
    }
    if (obs.consciousness) payload.consciousness = obs.consciousness;
    run(() => addRecoveryObs(caseObj.case_id, payload))
      .then(() => setObs({ bp_systolic: '', bp_diastolic: '', pulse: '', spo2: '', pain_score: '', consciousness: 'A' }));
  };

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      <section className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4" aria-label="Surgical team">
        <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Surgical team</h4>
        <ul className="mt-2 space-y-1 text-sm text-ink-700 dark:text-ink-300">
          {(caseObj.team_members || []).map((m) => (
            <li key={m.member_id} className="flex items-center justify-between gap-2">
              <span>{m.name || `User #${m.user_id}`} <span className="text-ink-400">— {m.role}</span></span>
              {!isTerminal && (
                <button type="button" disabled={busy} onClick={() => run(() => removeTeamMember(caseObj.case_id, m.member_id))}
                        className="text-xs text-rose-600 dark:text-rose-400 hover:underline">remove</button>
              )}
            </li>
          ))}
          {(caseObj.team_members || []).length === 0 && <li className="text-ink-400">No team recorded.</li>}
        </ul>
        {!isTerminal && (
          <form onSubmit={submitTeam} className="mt-3 flex flex-wrap items-end gap-2">
            <label className="block text-sm text-ink-700 dark:text-ink-300">
              Role
              <select value={team.role} onChange={(e) => setTeam((t) => ({ ...t, role: e.target.value }))} className="input mt-1">
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>
            <label className="block flex-1 text-sm text-ink-700 dark:text-ink-300">
              Name
              <input type="text" value={team.name} onChange={(e) => setTeam((t) => ({ ...t, name: e.target.value }))} className="input mt-1 w-full" />
            </label>
            <button type="submit" disabled={busy} className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">Add</button>
          </form>
        )}
      </section>

      <section className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4" aria-label="Consumables and implants">
        <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Consumables &amp; implants</h4>
        <ul className="mt-2 space-y-1 text-sm text-ink-700 dark:text-ink-300">
          {(caseObj.consumables || []).map((c) => (
            <li key={c.consumable_id}>• {c.item_name}{c.qty ? ` ×${c.qty}` : ''}{c.is_implant ? ` — implant${c.serial_no ? ` (${c.serial_no})` : ''}` : ''}</li>
          ))}
          {(caseObj.consumables || []).length === 0 && <li className="text-ink-400">None recorded.</li>}
        </ul>
        {!isTerminal && (
          <form onSubmit={submitCons} className="mt-3 flex flex-wrap items-end gap-2">
            <label className="block flex-1 text-sm text-ink-700 dark:text-ink-300">
              Item
              <input type="text" value={cons.item_name} onChange={(e) => setCons((c) => ({ ...c, item_name: e.target.value }))} className="input mt-1 w-full" />
            </label>
            <label className="block text-sm text-ink-700 dark:text-ink-300">
              Qty
              <input type="number" step="0.01" value={cons.qty} onChange={(e) => setCons((c) => ({ ...c, qty: e.target.value }))} className="input mt-1 w-20" />
            </label>
            <label className="flex items-center gap-1.5 text-sm text-ink-700 dark:text-ink-300">
              <input type="checkbox" checked={cons.is_implant} onChange={(e) => setCons((c) => ({ ...c, is_implant: e.target.checked }))} />
              Implant
            </label>
            {cons.is_implant && (
              <label className="block text-sm text-ink-700 dark:text-ink-300">
                Serial
                <input type="text" value={cons.serial_no} onChange={(e) => setCons((c) => ({ ...c, serial_no: e.target.value }))} className="input mt-1 w-28" />
              </label>
            )}
            <button type="submit" disabled={busy} className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">Add</button>
          </form>
        )}
      </section>

      {inRecovery && (
        <section className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4" aria-label="Recovery observations">
          <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Post-op recovery</h4>
          {(caseObj.recovery_observations || []).length > 0 && (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-ink-500 dark:text-ink-400">
                  <tr><th className="py-1">Time</th><th className="py-1">BP</th><th className="py-1">Pulse</th><th className="py-1">SpO₂</th><th className="py-1">Pain</th></tr>
                </thead>
                <tbody>
                  {caseObj.recovery_observations.map((o) => (
                    <tr key={o.obs_id} className="border-t border-ink-100 dark:border-ink-800">
                      <td className="py-1 text-ink-500 dark:text-ink-400">{o.recorded_at ? new Date(o.recorded_at).toLocaleTimeString() : '—'}</td>
                      <td className="py-1 text-ink-800 dark:text-ink-200">{o.bp_systolic ?? '—'}/{o.bp_diastolic ?? '—'}</td>
                      <td className="py-1 text-ink-800 dark:text-ink-200">{o.pulse ?? '—'}</td>
                      <td className="py-1 text-ink-800 dark:text-ink-200">{o.spo2 ?? '—'}</td>
                      <td className="py-1 text-ink-800 dark:text-ink-200">{o.pain_score ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <form onSubmit={submitObs} className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-6">
            {[['bp_systolic', 'BP sys'], ['bp_diastolic', 'BP dia'], ['pulse', 'Pulse'], ['spo2', 'SpO₂'], ['pain_score', 'Pain 0-10']].map(([k, label]) => (
              <label key={k} className="block text-xs text-ink-700 dark:text-ink-300">
                {label}
                <input type="number" value={obs[k]} onChange={(e) => setObs((o) => ({ ...o, [k]: e.target.value }))} className="input mt-1 w-full" />
              </label>
            ))}
            <label className="block text-xs text-ink-700 dark:text-ink-300">
              AVPU
              <select value={obs.consciousness} onChange={(e) => setObs((o) => ({ ...o, consciousness: e.target.value }))} className="input mt-1 w-full">
                {['A', 'V', 'P', 'U'].map((x) => <option key={x} value={x}>{x}</option>)}
              </select>
            </label>
            <div className="col-span-3 flex justify-end sm:col-span-6">
              <button type="submit" disabled={busy} className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">Record obs</button>
            </div>
          </form>
        </section>
      )}
    </div>
  );
}
