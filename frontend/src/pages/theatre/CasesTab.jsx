import { useCallback, useEffect, useState } from 'react';
import { Scissors } from 'lucide-react';
import { listCases, getCase } from './api';
import { errorText } from './errors';
import Worklist from '../../components/Worklist';
import CaseForm from './CaseForm';
import CaseBoard from './CaseBoard';

const STATUSES = ['Scheduled', 'InTheatre', 'Recovery', 'Completed', 'Cancelled'];
const STATUS_LABELS = { InTheatre: 'In theatre' };

const CHIP = {
  Scheduled: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  InTheatre: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
  Recovery: 'bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300',
  Completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  Cancelled: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
};

const shortTime = (iso) => {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const caseMeta = (c) => {
  if (c.priority === 'Emergency') return <span className="font-semibold text-rose-600 dark:text-rose-400">Emergency</span>;
  return shortTime(c.scheduled_at);
};

export default function CasesTab() {
  const [cases, setCases] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    listCases({})
      .then((rows) => { setCases(rows || []); setError(''); })
      .catch((err) => setError(errorText(err, 'Failed to load cases')));
  }, []);

  useEffect(() => { load(); }, [load]);

  const openCase = (row) => {
    getCase(row.case_id).then(setSelected).catch((err) => setError(errorText(err, 'Failed to open case')));
  };

  return (
    <>
      <Worklist
        items={cases}
        statuses={STATUSES}
        statusLabels={STATUS_LABELS}
        chipClass={CHIP}
        getKey={(c) => c.case_id}
        getStatus={(c) => c.status}
        primary={(c) => c.patient_name || `Patient #${c.patient_id}`}
        secondary={(c) => c.procedure_name}
        meta={caseMeta}
        searchText={(c) => `${c.patient_name || ''} ${c.procedure_name || ''}`}
        selectedKey={selected?.case_id}
        onSelect={openCase}
        onNew={() => setShowNew(true)}
        newLabel="New case"
        searchPlaceholder="Search cases by patient or procedure…"
        emptyTitle="No surgical cases yet."
        emptyHint="Book one with “New case”, or send a request from the Clinical Desk."
        error={error}
      >
        {selected ? (
          <CaseBoard caseObj={selected} onChanged={(updated) => { setSelected(updated); load(); }} />
        ) : (
          <div className="flex flex-col items-center gap-2 py-16 text-center">
            <Scissors size={30} className="text-ink-300 dark:text-ink-600" strokeWidth={1.5} />
            <p className="text-sm font-medium text-ink-600 dark:text-ink-300">Select a case to open its board</p>
            <p className="text-xs text-ink-500 dark:text-ink-400">Checklists, operative note, anaesthesia and billing live here.</p>
          </div>
        )}
      </Worklist>

      {showNew && (
        <CaseForm onClose={() => setShowNew(false)}
                  onSaved={(created) => { setShowNew(false); setSelected(created); load(); }} />
      )}
    </>
  );
}
