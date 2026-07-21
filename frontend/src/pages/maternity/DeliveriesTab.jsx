import { useCallback, useEffect, useRef, useState } from 'react';
import { listEpisodes, getEpisode, registerNewborn } from './api';
import DeliveryForm from './DeliveryForm';
import PncVisitForm from './PncVisitForm';
import { errorText } from './errors';

export default function DeliveriesTab() {
  const [active, setActive] = useState([]);
  const [delivered, setDelivered] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showDelivery, setShowDelivery] = useState(null);
  const [showPnc, setShowPnc] = useState(false);
  const [error, setError] = useState('');
  // Errors from actions taken inside the "Delivery detail" section (e.g.
  // registering a newborn as a patient) are shown next to that section
  // rather than in the far-away "Active pregnancies" panel.
  const [detailError, setDetailError] = useState('');
  // Tracks the episode_id of the most recently requested detail so that a
  // late-resolving (out-of-order) fetch for a since-abandoned selection can
  // never overwrite the deliveries/newborns shown for whichever episode is
  // selected now — a delivery/newborn list must never render under the
  // wrong patient's name.
  const requestedEpisodeIdRef = useRef(null);

  const refresh = useCallback(() => {
    Promise.resolve(listEpisodes({ status: 'Active' }))
      .then((rows) => setActive(rows || []))
      .catch(() => setError('Failed to load active episodes'));
    Promise.resolve(listEpisodes({ status: 'Delivered' }))
      .then((rows) => setDelivered(rows || []))
      .catch(() => setError('Failed to load delivered episodes'));
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const openEpisode = useCallback((id) => {
    setSelected(null); // clear stale detail immediately so it can never render under the wrong name
    requestedEpisodeIdRef.current = id;
    Promise.resolve(getEpisode(id))
      .then((ep) => {
        // Ignore out-of-order responses: only apply if this is still the
        // latest requested episode, and the payload actually matches it.
        if (requestedEpisodeIdRef.current !== id) return;
        if (ep && ep.episode_id !== id) return;
        setSelected(ep || null);
        setError('');
        setDetailError('');
      })
      .catch(() => {
        if (requestedEpisodeIdRef.current !== id) return;
        setError('Failed to load episode');
      });
  }, []);

  // `episodeId` is captured at click time (see call site) rather than read
  // from `selected` inside .then — if the user switches to viewing a
  // different episode while this request is in flight, `selected` (and
  // requestedEpisodeIdRef) will have moved on by the time this resolves.
  // Re-opening the now-stale `episodeId` here would discard whatever
  // episode the user has since navigated to (defeating the out-of-order
  // guard in openEpisode) and silently snap the view back. So only refresh
  // if the captured id still matches the currently-requested episode;
  // otherwise skip the refresh without re-navigating the user.
  const handleRegisterNewborn = (newbornId, episodeId) => {
    Promise.resolve(registerNewborn(newbornId))
      .then(() => {
        if (requestedEpisodeIdRef.current === episodeId) openEpisode(episodeId);
      })
      .catch((err) => setDetailError(errorText(err, 'Failed to register newborn')));
  };

  const deliveries = selected?.deliveries || [];
  const pncVisits = selected?.pnc_visits || [];

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <section
        aria-label="Active pregnancies"
        className="rounded-2xl border border-ink-200/70 dark:border-ink-800 bg-white dark:bg-ink-900 shadow-soft p-4"
      >
        <h2 className="text-sm font-semibold text-ink-900 dark:text-white">Active pregnancies</h2>
        {error && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{error}</p>}
        <ul className="mt-3 divide-y divide-ink-100 dark:divide-ink-800">
          {active.map((ep) => (
            <li key={ep.episode_id} className="flex items-center justify-between py-2">
              <span className="font-medium text-ink-900 dark:text-white">{ep.patient_name}</span>
              <button
                type="button"
                data-tour="mat-delivery"
                onClick={() => setShowDelivery(ep.episode_id)}
                className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
              >
                Record delivery
              </button>
            </li>
          ))}
          {active.length === 0 && (
            <li className="py-2 text-sm text-ink-500 dark:text-ink-400">No active pregnancies.</li>
          )}
        </ul>
      </section>

      <section
        aria-label="Delivered episodes"
        className="rounded-2xl border border-ink-200/70 dark:border-ink-800 bg-white dark:bg-ink-900 shadow-soft p-4"
      >
        <h2 className="text-sm font-semibold text-ink-900 dark:text-white">Delivered</h2>
        <ul className="mt-3 divide-y divide-ink-100 dark:divide-ink-800">
          {delivered.map((ep) => (
            <li key={ep.episode_id}>
              <button
                type="button"
                onClick={() => openEpisode(ep.episode_id)}
                className="w-full rounded-lg px-2 py-2 text-left hover:bg-ink-50 dark:hover:bg-ink-800/50"
              >
                <span className="font-medium text-ink-900 dark:text-white">{ep.patient_name}</span>
              </button>
            </li>
          ))}
          {delivered.length === 0 && (
            <li className="py-2 text-sm text-ink-500 dark:text-ink-400">No delivered episodes yet.</li>
          )}
        </ul>
      </section>

      {selected && (
        <section
          aria-label="Delivery detail"
          className="md:col-span-2 rounded-2xl border border-ink-200/70 dark:border-ink-800 bg-white dark:bg-ink-900 shadow-soft p-4"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ink-900 dark:text-white">{selected.patient_name}</h2>
            <button
              type="button"
              data-tour="mat-pnc-visit"
              onClick={() => setShowPnc(true)}
              className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
            >
              New PNC visit
            </button>
          </div>
          {detailError && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{detailError}</p>}

          {deliveries.map((d) => (
            <div key={d.delivery_id} className="mt-3">
              <p className="text-sm text-ink-700 dark:text-ink-300">
                {d.mode} · {new Date(d.delivered_at).toLocaleString()} · Mother: {d.mother_status}
                {d.blood_loss_ml != null ? ` · Blood loss ${d.blood_loss_ml} ml` : ''}
              </p>
              <table className="mt-2 w-full text-sm">
                <thead>
                  <tr className="text-left text-ink-500 dark:text-ink-400">
                    <th className="py-1 pr-2 font-medium">#</th>
                    <th className="py-1 pr-2 font-medium">Sex</th>
                    <th className="py-1 pr-2 font-medium">Weight (g)</th>
                    <th className="py-1 pr-2 font-medium">APGAR</th>
                    <th className="py-1 pr-2 font-medium">Outcome</th>
                    <th className="py-1 font-medium">Patient</th>
                  </tr>
                </thead>
                <tbody className="text-ink-900 dark:text-white">
                  {(d.newborns || []).map((n) => (
                    <tr key={n.newborn_id} className="border-t border-ink-100 dark:border-ink-800">
                      <td className="py-1 pr-2">{n.birth_order}</td>
                      <td className="py-1 pr-2">{n.sex}</td>
                      <td className="py-1 pr-2">{n.weight_g ?? '—'}</td>
                      <td className="py-1 pr-2">{n.apgar_1 ?? '—'}/{n.apgar_5 ?? '—'}</td>
                      <td className="py-1 pr-2">{n.outcome}</td>
                      <td className="py-1">
                        {n.registered_patient_id ? (
                          <span className="text-ink-500 dark:text-ink-400">Patient #{n.registered_patient_id}</span>
                        ) : (
                          <button
                            type="button"
                            data-tour="mat-register-newborn"
                            disabled={n.outcome !== 'Live'}
                            onClick={() => handleRegisterNewborn(n.newborn_id, selected.episode_id)}
                            className="rounded-lg border border-ink-200 dark:border-ink-800 px-2 py-1 text-xs font-medium text-ink-700 dark:text-ink-300 hover:bg-ink-50 dark:hover:bg-ink-800/50 disabled:opacity-60"
                          >
                            Register as patient
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {deliveries.length === 0 && (
            <p className="mt-3 text-sm text-ink-500 dark:text-ink-400">No deliveries recorded.</p>
          )}

          <h3 className="mt-4 text-sm font-semibold text-ink-900 dark:text-white">PNC visits</h3>
          <table className="mt-2 w-full text-sm">
            <thead>
              <tr className="text-left text-ink-500 dark:text-ink-400">
                <th className="py-1 pr-2 font-medium">#</th>
                <th className="py-1 pr-2 font-medium">Date</th>
                <th className="py-1 pr-2 font-medium">BP</th>
                <th className="py-1 pr-2 font-medium">Involution</th>
                <th className="py-1 font-medium">Feeding</th>
              </tr>
            </thead>
            <tbody className="text-ink-900 dark:text-white">
              {pncVisits.map((v) => (
                <tr key={v.visit_id} className="border-t border-ink-100 dark:border-ink-800">
                  <td className="py-1 pr-2">{v.visit_number}</td>
                  <td className="py-1 pr-2">{v.visit_date}</td>
                  <td className="py-1 pr-2">{v.bp_systolic ? `${v.bp_systolic}/${v.bp_diastolic}` : '—'}</td>
                  <td className="py-1 pr-2">{v.involution ?? '—'}</td>
                  <td className="py-1">{v.feeding ?? '—'}</td>
                </tr>
              ))}
              {pncVisits.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-2 text-ink-500 dark:text-ink-400">No PNC visits recorded yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      )}

      {showDelivery != null && (
        <DeliveryForm
          episodeId={showDelivery}
          onClose={() => setShowDelivery(null)}
          onSaved={() => { setShowDelivery(null); refresh(); }}
        />
      )}
      {showPnc && selected && (
        <PncVisitForm
          episodeId={selected.episode_id}
          onClose={() => setShowPnc(false)}
          onSaved={() => { setShowPnc(false); openEpisode(selected.episode_id); }}
        />
      )}
    </div>
  );
}
