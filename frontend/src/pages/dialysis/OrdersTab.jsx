import { useCallback, useEffect, useState } from 'react';
import { Droplets } from 'lucide-react';
import { listOrders, getOrder } from './api';
import { errorText } from './errors';
import Worklist from '../../components/Worklist';
import OrderForm from './OrderForm';
import SessionBoard from './SessionBoard';

const STATUSES = ['Ordered', 'Connected', 'Disconnected', 'Completed', 'Cancelled'];

const CHIP = {
  Ordered: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  Connected: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  Disconnected: 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300',
  Completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  Cancelled: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
};

const shortTime = (iso) => {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

export default function OrdersTab() {
  const [orders, setOrders] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    // Promise-chain (not async/await) so the effect calling load() has no
    // setState in its synchronous path — matches the maternity tabs' convention.
    listOrders({})
      .then((rows) => { setOrders(rows || []); setError(''); })
      .catch((err) => setError(errorText(err, 'Failed to load dialysis sessions')));
  }, []);

  useEffect(() => { load(); }, [load]);

  const openOrder = (row) => {
    getOrder(row.order_id)
      .then(setSelected)
      .catch((err) => setError(errorText(err, 'Failed to open session')));
  };

  return (
    <>
      <Worklist
        items={orders}
        statuses={STATUSES}
        chipClass={CHIP}
        getKey={(o) => o.order_id}
        getStatus={(o) => o.status}
        primary={(o) => o.patient_name || `Patient #${o.patient_id}`}
        secondary={(o) => `Treatment #${o.treatment_no}`}
        meta={(o) => shortTime(o.scheduled_at)}
        searchText={(o) => `${o.patient_name || ''} treatment ${o.treatment_no || ''}`}
        selectedKey={selected?.order_id}
        onSelect={openOrder}
        onNew={() => setShowNew(true)}
        newLabel="New session"
        searchPlaceholder="Search sessions by patient…"
        emptyTitle="No dialysis sessions yet."
        emptyHint="Start one with “New session”."
        error={error}
      >
        {selected ? (
          <SessionBoard order={selected} onChanged={(updated) => { setSelected(updated); load(); }} />
        ) : (
          <div className="flex flex-col items-center gap-2 py-16 text-center">
            <Droplets size={30} className="text-ink-300 dark:text-ink-600" strokeWidth={1.5} />
            <p className="text-sm font-medium text-ink-600 dark:text-ink-300">Select a session to open its board</p>
            <p className="text-xs text-ink-500 dark:text-ink-400">Safety checklist, observations and adequacy (Kt/V) live here.</p>
          </div>
        )}
      </Worklist>

      {showNew && (
        <OrderForm onClose={() => setShowNew(false)}
                   onSaved={(created) => { setShowNew(false); setSelected(created); load(); }} />
      )}
    </>
  );
}
