import { useState } from 'react';
import AncClinicTab from './maternity/AncClinicTab';
import LaborBoardTab from './maternity/LaborBoardTab';
import DeliveriesTab from './maternity/DeliveriesTab';

const TABS = [
  { key: 'anc', label: 'ANC Clinic' },
  { key: 'labor', label: 'Labor Board' },
  { key: 'deliveries', label: 'Deliveries & PNC' },
];

export default function Maternity() {
  const [tab, setTab] = useState('anc');
  return (
    <div className="p-4 md:p-6">
      <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">Maternity</h1>
      <div className="mt-4 flex gap-2 border-b border-gray-200 dark:border-gray-700" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm font-medium rounded-t-md ${
              tab === t.key
                ? 'bg-white dark:bg-gray-800 border border-b-0 border-gray-200 dark:border-gray-700 text-blue-600 dark:text-blue-400'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="mt-4">
        {tab === 'anc' && <AncClinicTab />}
        {tab === 'labor' && <LaborBoardTab />}
        {tab === 'deliveries' && <DeliveriesTab />}
      </div>
    </div>
  );
}
