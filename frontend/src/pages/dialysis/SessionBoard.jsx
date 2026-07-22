import { useState } from 'react';
import {
  addChecklistRun, addComplication, cancelOrder, completeOrder,
  connectOrder, disconnectOrder, getOrder,
} from './api';
import { errorText } from './errors';
import ObservationForm from './ObservationForm';
import AdequacyPanel from './AdequacyPanel';
import FlowChart from './FlowChart';

const FLOW = ['Ordered', 'Connected', 'Disconnected', 'Completed'];
const COMPLICATION_TYPES = [
  'Hypotension', 'Cramps', 'Nausea', 'Vomiting', 'Clotting',
  'Bleeding', 'Chest-pain', 'Fever', 'Disequilibrium',
];

function Stepper({ status }) {
  const cancelled = status === 'Cancelled';
  const idx = FLOW.indexOf(status);
  return (
    <ol className="flex items-center gap-2 text-xs" aria-label="Session progress">
      {FLOW.map((s, i) => {
        const done = !cancelled && i <= idx;
        return (
          <li key={s} className={`rounded-full px-2.5 py-1 font-medium ${
            done ? 'bg-brand-600 text-white' : 'bg-ink-100 dark:bg-ink-800 text-ink-500 dark:text-ink-400'
          }`}>{s}</li>
        );
      })}
      {cancelled && <li className="rounded-full bg-rose-600 px-2.5 py-1 font-medium text-white">Cancelled</li>}
    </ol>
  );
}

export default function SessionBoard({ order, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showObs, setShowObs] = useState(false);
  const [comp, setComp] = useState({ type: 'Hypotension', intervention: '' });

  const passedChecklist = (order.checklist_runs || []).some((r) => r.passed);
  const isTerminal = order.status === 'Completed' || order.status === 'Cancelled';

  const run = async (fn) => {
    setBusy(true);
    setError('');
    try {
      await fn();
      const fresh = await getOrder(order.order_id);
      onChanged(fresh);
    } catch (err) {
      setError(errorText(err, 'Action failed'));
    } finally {
      setBusy(false);
    }
  };

  const doCancel = () => {
    const reason = window.prompt('Reason for cancelling this session?');
    if (!reason) return;
    run(() => cancelOrder(order.order_id, { reason }));
  };

  const submitComplication = (e) => {
    e.preventDefault();
    run(() => addComplication(order.order_id, {
      type: comp.type, intervention: comp.intervention || undefined,
    })).then(() => setComp({ type: 'Hypotension', intervention: '' }));
  };

  return (
    <section className="space-y-4" aria-label="Session detail">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-ink-900 dark:text-white">
            {order.patient_name || `Patient #${order.patient_id}`} · Treatment #{order.treatment_no}
          </div>
          <div className="mt-1"><Stepper status={order.status} /></div>
        </div>
        <div className="flex flex-wrap gap-2">
          {order.status === 'Ordered' && (
            <>
              <button type="button" disabled={busy} onClick={() => run(() => addChecklistRun(order.order_id, { passed: true }))}
                      className="rounded-lg border border-ink-200 dark:border-ink-800 px-3 py-1.5 text-sm font-medium text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50">
                Pass checklist
              </button>
              <button type="button" disabled={busy || !passedChecklist} title={passedChecklist ? '' : 'Pass the safety checklist first'}
                      onClick={() => run(() => connectOrder(order.order_id))}
                      className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
                Connect
              </button>
            </>
          )}
          {order.status === 'Connected' && (
            <>
              <button type="button" disabled={busy} onClick={() => setShowObs(true)}
                      className="rounded-lg border border-ink-200 dark:border-ink-800 px-3 py-1.5 text-sm font-medium text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50">
                Add observation
              </button>
              <button type="button" disabled={busy} onClick={() => run(() => disconnectOrder(order.order_id))}
                      className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
                Disconnect
              </button>
            </>
          )}
          {order.status === 'Disconnected' && (
            <button type="button" disabled={busy} onClick={() => run(() => completeOrder(order.order_id))}
                    className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
              Complete
            </button>
          )}
          {!isTerminal && (
            <button type="button" disabled={busy} onClick={doCancel}
                    className="rounded-lg border border-rose-300 dark:border-rose-800 px-3 py-1.5 text-sm font-medium text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-900/20">
              Cancel
            </button>
          )}
        </div>
      </div>
      {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      <div>
        <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Intradialytic trend</h4>
        <div className="mt-2"><FlowChart observations={order.observations || []} /></div>
      </div>

      {(order.observations || []).length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-ink-200/70 dark:border-ink-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-ink-50 dark:bg-ink-800/40 text-xs uppercase text-ink-500 dark:text-ink-400">
              <tr><th className="px-3 py-2">Time</th><th className="px-3 py-2">BP</th><th className="px-3 py-2">Pulse</th><th className="px-3 py-2">UF mL</th></tr>
            </thead>
            <tbody>
              {order.observations.map((o) => (
                <tr key={o.obs_id} className="border-t border-ink-100 dark:border-ink-800">
                  <td className="px-3 py-2 text-ink-500 dark:text-ink-400">{o.recorded_at ? new Date(o.recorded_at).toLocaleTimeString() : '—'}</td>
                  <td className="px-3 py-2 text-ink-800 dark:text-ink-200">{o.bp_systolic ?? '—'}/{o.bp_diastolic ?? '—'}</td>
                  <td className="px-3 py-2 text-ink-800 dark:text-ink-200">{o.pulse ?? '—'}</td>
                  <td className="px-3 py-2 text-ink-800 dark:text-ink-200">{o.uf_volume_ml ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AdequacyPanel order={order} onSaved={() => run(() => Promise.resolve())} />

      <section className="rounded-xl border border-ink-200/70 dark:border-ink-800 p-4" aria-label="Complications">
        <h4 className="text-sm font-semibold text-ink-900 dark:text-white">Complications</h4>
        <ul className="mt-2 space-y-1 text-sm text-ink-700 dark:text-ink-300">
          {(order.complications || []).map((c) => (
            <li key={c.complication_id}>• {c.type}{c.intervention ? ` — ${c.intervention}` : ''}</li>
          ))}
          {(order.complications || []).length === 0 && <li className="text-ink-400">None recorded.</li>}
        </ul>
        {!isTerminal && (
          <form onSubmit={submitComplication} className="mt-3 flex flex-wrap items-end gap-2">
            <label className="block text-sm text-ink-700 dark:text-ink-300">
              Type
              <select value={comp.type} onChange={(e) => setComp((c) => ({ ...c, type: e.target.value }))} className="input mt-1">
                {COMPLICATION_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label className="block flex-1 text-sm text-ink-700 dark:text-ink-300">
              Intervention
              <input type="text" value={comp.intervention} onChange={(e) => setComp((c) => ({ ...c, intervention: e.target.value }))} className="input mt-1 w-full" />
            </label>
            <button type="submit" disabled={busy}
                    className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60">
              Add
            </button>
          </form>
        )}
      </section>

      {showObs && (
        <ObservationForm orderId={order.order_id} onClose={() => setShowObs(false)}
                         onSaved={() => { setShowObs(false); run(() => Promise.resolve()); }} />
      )}
    </section>
  );
}
