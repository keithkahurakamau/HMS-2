import React, { useState, useEffect, useMemo } from 'react';
import {} from 'react-router-dom';
import { apiClient } from '../api/client';
import {
    Microscope, Clock, AlertCircle,
    Printer, XCircle, TestTube, FileDigit,
    Settings, Activity, FlaskConical, Send, Package, Plus, Trash2,
    Pencil, Save, X, RefreshCcw, FileText, Paperclip, UserPlus, History, ClipboardList } from 'lucide-react';
import toast from 'react-hot-toast';
import { printLabReport } from '../utils/printTemplates';
import { printVisitSummary, printLabReport as printPatientLabReport } from '../utils/printReports';
import PageHeader from '../components/PageHeader';
import QueuePatientsModal from '../components/QueuePatientsModal';
import { useAuth } from '../context/AuthContext';
import PatientDetailsHeader from './clinical/PatientDetailsHeader';
import DepartmentQueue from '../components/DepartmentQueue';
import ActionsMenu from './clinical/ActionsMenu';
import FilesModal from './clinical/modals/FilesModal';
import QueuePatientModal from './clinical/modals/QueuePatientModal';
import PatientHistoryModal from '../components/PatientHistoryModal';

/* ────────────────────────────────────────────────────────────────────────── */
/*  Laboratory                                                                */
/*                                                                            */
/*  The lab module is fully driven by `lab_test_catalog` + `lab_catalog_      */
/*  parameters`. Adding a new test (with whatever discrete result fields it   */
/*  has) is purely a data operation — no front-end changes required.          */
/*  Reagents that are reusable (slides, glassware, probes) are logged on use  */
/*  but don't decrement stock.                                                */
/* ────────────────────────────────────────────────────────────────────────── */

const EMPTY_CATALOG_FORM = {
    test_name: '', description: '', category: 'Hematology',
    default_specimen_type: 'Blood', base_price: 0, turnaround_hours: 24,
    is_active: true, requires_barcode: false, parameters: [] };

const EMPTY_PARAMETER = {
    key: '', name: '', unit: '', value_type: 'number',
    choices: '', ref_low: '', ref_high: '', sort_order: 0, is_active: true };

// Pure result-flagging helper — hoisted to module scope.
const flagFor = (val, low, high) => {
    if (val === '' || val == null) return null;
    const n = parseFloat(val);
    if (isNaN(n)) return null;
    if (low != null && n < low) return <span className="badge-info">Low</span>;
    if (high != null && n > high) return <span className="badge-danger">High</span>;
    return <span className="badge-success">Normal</span>;
};

export default function Laboratory() {
    const auth = useAuth();
    const perms = auth?.user?.permissions || [];
    const hasPerm = (p) => perms.includes(p);

    const [activeTab, setActiveTab] = useState('queue');
    const [isLoading, setIsLoading] = useState(true);

    // ── Domain state ───────────────────────────────────────────────────────
    const [catalog, setCatalog] = useState([]);
    const [queue, setQueue] = useState([]);
    const [labInventory, setLabInventory] = useState([]);

    // ── Workspace state ────────────────────────────────────────────────────
    // The lab queue is a flat list of test orders; the workbench is patient-
    // centric (pick a patient → their requested tests → one test's results), so
    // we track the selected patient key alongside the active test.
    const [activePatientKey, setActivePatientKey] = useState(null);
    const [activeTest, setActiveTest] = useState(null);
    const [results, setResults] = useState({});
    const [techNotes, setTechNotes] = useState('');
    const [consumedItems, setConsumedItems] = useState([]);
    const [selectedBatchId, setSelectedBatchId] = useState('');
    const [consumeQty, setConsumeQty] = useState('');

    // ── Consolidated Actions ▾ / secondary surfaces ─────────────────────────
    const [actionModal, setActionModal] = useState(null); // 'files' | 'queue' | null
    const [historyModal, setHistoryModal] = useState(null); // { entry_type } | null

    // ── Catalog editor state ───────────────────────────────────────────────
    const [editorOpen, setEditorOpen] = useState(false);
    const [editing, setEditing] = useState(null);   // catalog row being edited (null = create)
    const [catalogForm, setCatalogForm] = useState(EMPTY_CATALOG_FORM);

    useEffect(() => { fetchLaboratoryData(); }, []);

    // "View all patients" opens the full queue in place. It used to navigate to
    // the registry, which lost the clinician's place in the workspace and did
    // not actually show who was waiting.
    const [showQueueModal, setShowQueueModal] = useState(false);
    const [isClearingQueue, setIsClearingQueue] = useState(false);

    const handleClearQueue = async () => {
        setIsClearingQueue(true);
        try {
            const res = await apiClient.post('/queue/end-of-day', { department: 'Laboratory' });
            const n = res.data?.checked_out ?? 0;
            toast.success(n > 0
                ? `${n} patient(s) removed from the queue.`
                : 'The queue was already empty.');
            setShowQueueModal(false);
            
            fetchLaboratoryData();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Could not clear the queue.');
        } finally {
            setIsClearingQueue(false);
        }
    };

    const fetchLaboratoryData = async () => {
        setIsLoading(true);
        try {
            const [queueRes, invRes, catRes] = await Promise.all([
                apiClient.get('/laboratory/queue').catch(() => ({ data: [] })),
                apiClient.get('/laboratory/inventory').catch(() => ({ data: [] })),
                apiClient.get('/laboratory/catalog?include_inactive=true').catch(() => ({ data: [] })),
            ]);
            setQueue(queueRes.data || []);
            setLabInventory(invRes.data || []);
            setCatalog(catRes.data || []);
        } catch {
            toast.error('Failed to sync laboratory data.');
        } finally {
            setIsLoading(false);
        }
    };

    /* ─── Workspace helpers ──────────────────────────────────────────────── */

    // Collapse the flat test queue into one row per patient (the screen is
    // patient-centric: pick a patient → see their requested tests). The patient
    // key is patient_id when present, else the display name.
    const patientGroups = useMemo(() => {
        const byKey = new Map();
        queue.forEach((t) => {
            const key = t.patient_id != null ? `p${t.patient_id}` : `n:${t.patient}`;
            let g = byKey.get(key);
            if (!g) {
                g = {
                    key,
                    patient_id: t.patient_id,
                    patient_name: t.patient,
                    outpatient_no: t.outpatient_no,
                    joined_at: t.joined_at || t.requested_at,
                    priority: 'Normal',
                    tests: [] };
                byKey.set(key, g);
            }
            g.tests.push(t);
            if (t.priority === 'STAT') g.priority = 'Critical';
            // Keep the earliest request time as the patient's wait start.
            if (t.joined_at && (!g.joined_at || t.joined_at < g.joined_at)) g.joined_at = t.joined_at;
        });
        return Array.from(byKey.values());
    }, [queue]);

    const activePatientGroup = useMemo(
        () => patientGroups.find((g) => g.key === activePatientKey) || null,
        [patientGroups, activePatientKey],
    );

    // Header rows: one per patient (Q.No · OPD · Name · From · Mins).
    const headerQueue = patientGroups.map((g) => ({
        queue_id: g.key,
        patient_id: g.patient_id,
        patient_name: g.patient_name,
        outpatient_no: g.outpatient_no,
        joined_at: g.joined_at,
        triage_time: g.joined_at ? new Date(g.joined_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : null,
        priority: g.priority }));
    const headerPatient = activePatientGroup ? {
        patient_name: activePatientGroup.patient_name,
        outpatient_no: activePatientGroup.outpatient_no,
        queue_id: activePatientGroup.key } : null;

    const activeCatalog = useMemo(
        () => catalog.find(c => c.catalog_id === activeTest?.catalog_id),
        [catalog, activeTest],
    );

    const activeParameters = useMemo(
        () => (activeCatalog?.parameters || []).filter(p => p.is_active),
        [activeCatalog],
    );

    const loadTest = (test) => {
        setActiveTest(test);
        setResults({});
        setTechNotes('');
        setConsumedItems([]);
    };

    // Selecting a patient from the header queue opens their first requested test.
    const handlePatientSelect = (item) => {
        const group = patientGroups.find((g) => g.key === item.queue_id);
        if (!group) return;
        setActivePatientKey(group.key);
        loadTest(group.tests[0] || null);
    };

    // After a test leaves the queue (removed / rejected / released), advance to
    // the patient's next remaining test, or clear the workspace if none remain.
    const afterTestRemoved = (testId) => {
        const remaining = (activePatientGroup?.tests || []).filter((t) => t.test_id !== testId);
        if (remaining.length) {
            loadTest(remaining[0]);
        } else {
            setActiveTest(null);
            setActivePatientKey(null);
        }
    };

    // Remove a pending test from the queue (ordered in error / no longer needed).
    const handleCancelTest = async (order) => {
        if (!window.confirm(`Remove "${order.test_name}" for ${order.patient_name || order.patient} from the lab queue?`)) return;
        try {
            await apiClient.post(`/laboratory/tests/${order.test_id}/cancel`, { reason: null });
            toast.success('Test removed from the queue.');
            setQueue((prev) => prev.filter((q) => q.test_id !== order.test_id));
            if (activeTest?.test_id === order.test_id) afterTestRemoved(order.test_id);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Could not remove the test.');
        }
    };

    const handleCollectSpecimen = async () => {
        if (!activeTest) return;
        try {
            const res = await apiClient.post(`/laboratory/tests/${activeTest.test_id}/collect`, {});
            toast.success(`Specimen received — barcode ${res.data.specimen_id}`);
            const next = { ...activeTest, status: 'In Progress', specimen_id: res.data.specimen_id };
            setActiveTest(next);
            setQueue(queue.map(q => q.test_id === activeTest.test_id ? { ...q, status: 'In Progress' } : q));
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to mark specimen collected.');
        }
    };

    const handleSkipBarcode = () => {
        if (!activeTest) return;
        setActiveTest({ ...activeTest, status: 'In Progress' });
        setQueue(queue.map(q => q.test_id === activeTest.test_id ? { ...q, status: 'In Progress' } : q));
        toast('Barcode skipped — processing in single-step mode.', { icon: '⏭' });
    };

    /* ─── Reagent consumption ────────────────────────────────────────────── */

    const addConsumedItem = () => {
        if (!selectedBatchId) return;
        const inv = labInventory.find(i => i.batch_id === parseInt(selectedBatchId));
        if (!inv) return;

        const qty = inv.is_reusable ? 0 : parseInt(consumeQty || '0');
        if (!inv.is_reusable && (!qty || qty <= 0)) return;
        if (!inv.is_reusable && qty > inv.stock) {
            return toast.error(`Only ${inv.stock} available in this batch.`);
        }

        const existing = consumedItems.find(c => c.batch_id === inv.batch_id);
        if (existing) {
            setConsumedItems(consumedItems.map(c =>
                c.batch_id === inv.batch_id
                    ? { ...c, quantity: inv.is_reusable ? 0 : c.quantity + qty }
                    : c,
            ));
        } else {
            setConsumedItems([...consumedItems, { ...inv, quantity: qty }]);
        }
        setSelectedBatchId('');
        setConsumeQty('');
    };

    const removeConsumedItem = (batch_id) => {
        setConsumedItems(consumedItems.filter(c => c.batch_id !== batch_id));
    };

    /* ─── Submit / reject ────────────────────────────────────────────────── */

    const handleRejectSample = async () => {
        if (!activeTest) return;
        const reason = window.prompt('Reason for rejecting this sample (e.g. haemolysis, wrong specimen, insufficient volume):');
        if (!reason) return;
        try {
            await apiClient.post(`/laboratory/tests/${activeTest.test_id}/reject`, { reason });
            toast.success('Sample rejected.');
            const removedId = activeTest.test_id;
            setQueue(queue.filter(q => q.test_id !== removedId));
            afterTestRemoved(removedId);
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Reject failed.');
        }
    };

    const handleReleaseResults = async () => {
        const payload = {
            result_data: results,
            tech_notes: techNotes,
            consumed_items: consumedItems.map(c => ({ batch_id: c.batch_id, quantity: c.quantity })) };
        try {
            await apiClient.post(`/laboratory/tests/${activeTest.test_id}/complete`, payload);
            toast.success('Results released & stock reconciled.');
            const removedId = activeTest.test_id;
            setQueue(queue.filter(q => q.test_id !== removedId));
            afterTestRemoved(removedId);
            fetchLaboratoryData();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to commit results.');
        }
    };

    /* ─── Reports + consolidated Actions ▾ ───────────────────────────────── */

    const printPatient = () => ({
        full_name: activePatientGroup?.patient_name,
        outpatient_no: activePatientGroup?.outpatient_no,
        patient_id: activePatientGroup?.patient_id });

    // Lab Report — the patient's tests, printed via the shared list report.
    const handleLabReport = () => {
        if (!activePatientGroup?.patient_id) { toast.error('This queue row has no linked patient record.'); return; }
        apiClient.get('/laboratory/tests', { params: { patient_id: activePatientGroup.patient_id } })
            .then((r) => printPatientLabReport({ patient: printPatient(), tests: r.data || [] }))
            .catch((e) => toast.error(e.response?.data?.detail || 'Could not load lab tests.'));
    };

    // Visit Summary — patient context + the requested tests as investigations.
    const handleVisitSummary = () => {
        if (!activePatientGroup) return;
        printVisitSummary({
            patient: printPatient(),
            encounter: {
                date: new Date(),
                investigations: activePatientGroup.tests.map((t) => t.test_name) } });
    };

    // Consolidated Actions ▾ — mirrors MedicentreV3's Laboratory menu; perm-
    // gated (empty groups disappear). Approve-as-a-second-step, Unlock Lab
    // Request, and the Test-Per-Page report are follow-ups (no backend yet).
    const actionGroups = [
        { label: 'Requests', items: [
            { label: 'View Requests', icon: ClipboardList, perm: 'laboratory:read', onClick: () => setHistoryModal({ entry_type: 'lab' }) },
            { label: 'View Previous Visits', icon: History, perm: 'laboratory:read', onClick: () => setHistoryModal({ entry_type: 'visits' }) },
        ] },
        { label: 'Flow', items: [
            { label: 'Queue Patient', icon: UserPlus, perm: 'patients:write', onClick: () => setActionModal('queue') },
        ] },
        { label: 'Documents', items: [
            { label: 'Files', icon: Paperclip, perm: 'laboratory:read', onClick: () => setActionModal('files') },
            { label: 'Lab Report', icon: Printer, perm: 'laboratory:read', onClick: handleLabReport },
            { label: 'Visit Summary', icon: FileText, perm: 'laboratory:read', onClick: handleVisitSummary },
        ] },
    ];

    /* ─── Catalog editor ─────────────────────────────────────────────────── */

    const startEdit = (row) => {
        setEditing(row);
        setCatalogForm({
            ...EMPTY_CATALOG_FORM,
            ...row,
            base_price: Number(row.base_price || 0),
            parameters: (row.parameters || []).map(p => ({ ...p, _uid: crypto.randomUUID() })) });
        setEditorOpen(true);
    };

    const startCreate = () => {
        setEditing(null);
        setCatalogForm(EMPTY_CATALOG_FORM);
        setEditorOpen(true);
    };

    const addParamRow = () => setCatalogForm(f => ({ ...f, parameters: [...f.parameters, { ...EMPTY_PARAMETER, _uid: crypto.randomUUID() }] }));
    const removeParamRow = (idx) => setCatalogForm(f => ({ ...f, parameters: f.parameters.filter((_, i) => i !== idx) }));
    const setParamField = (idx, field, val) =>
        setCatalogForm(f => ({
            ...f,
            parameters: f.parameters.map((p, i) => (i === idx ? { ...p, [field]: val } : p)) }));

    const saveCatalog = async () => {
        const body = {
            ...catalogForm,
            base_price: parseFloat(catalogForm.base_price) || 0,
            turnaround_hours: parseInt(catalogForm.turnaround_hours) || 24,
            parameters: catalogForm.parameters.map(({ _uid, ...p }) => ({
                ...p,
                ref_low: p.ref_low === '' ? null : parseFloat(p.ref_low),
                ref_high: p.ref_high === '' ? null : parseFloat(p.ref_high),
                sort_order: parseInt(p.sort_order) || 0 })) };
        try {
            if (editing) {
                const { parameters, ...patch } = body;
                await apiClient.patch(`/laboratory/catalog/${editing.catalog_id}`, patch);
                // Sync parameters: add new ones, update existing
                await Promise.all(parameters.map((p) =>
                    p.parameter_id
                        ? apiClient.patch(`/laboratory/parameters/${p.parameter_id}`, p)
                        : apiClient.post(`/laboratory/catalog/${editing.catalog_id}/parameters`, p)
                ));
                toast.success('Test catalog entry updated.');
            } else {
                await apiClient.post('/laboratory/catalog', body);
                toast.success('Test catalog entry created.');
            }
            setEditorOpen(false);
            fetchLaboratoryData();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Save failed.');
        }
    };

    const deactivateCatalog = async (row) => {
        if (!window.confirm(`Deactivate "${row.test_name}"? Existing orders are unaffected; new orders won't be allowed.`)) return;
        try {
            await apiClient.delete(`/laboratory/catalog/${row.catalog_id}`);
            toast.success(`${row.test_name} deactivated.`);
            fetchLaboratoryData();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Deactivation failed.');
        }
    };

    /* ─── Render ─────────────────────────────────────────────────────────── */

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">
            <PageHeader
                eyebrow="Diagnostics"
                icon={TestTube}
                title="Laboratory"
                subtitle="Process orders, capture results, and publish reports — with full sample lifecycle tracking."
            />

            {/* Tabs */}
            <div data-tour="lab-tabs" className="card p-2 flex items-center justify-between shrink-0">
                <div role="tablist" aria-label="Laboratory mode" className="flex bg-ink-100/70 p-1 rounded-xl w-full max-w-md">
                    <button type="button" role="tab" aria-selected={activeTab === 'queue'} onClick={() => setActiveTab('queue')}
                            className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium transition-all ${activeTab === 'queue' ? 'bg-white dark:bg-ink-900 text-ink-900 dark:text-ink-100 shadow-soft ring-1 ring-ink-200/70' : 'text-ink-600 dark:text-ink-400 hover:text-ink-900'}`}>
                        <Microscope size={16} className={activeTab === 'queue' ? 'text-brand-600' : 'text-ink-400'} /> Lab Operations
                    </button>
                    <button type="button" role="tab" aria-selected={activeTab === 'catalog'} onClick={() => setActiveTab('catalog')}
                            className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium transition-all ${activeTab === 'catalog' ? 'bg-white dark:bg-ink-900 text-ink-900 dark:text-ink-100 shadow-soft ring-1 ring-ink-200/70' : 'text-ink-600 dark:text-ink-400 hover:text-ink-900'}`}>
                        <FileDigit size={16} className={activeTab === 'catalog' ? 'text-accent-600' : 'text-ink-400'} /> Test Catalog
                    </button>
                </div>
            </div>

            {/* ─────────────── Mode 1: Lab Operations ─────────────── */}
            {activeTab === 'queue' && (
                <>
                    {/* Patients routed here via the shared queue (sent to Laboratory) */}
                    <DepartmentQueue department="Laboratory" inline onChange={fetchLaboratoryData} />
                    {/* Patient details + laboratory queue (shared DoctorV2 header) */}
                    <div data-tour="lab-queue" className="shrink-0 z-20">
                        <PatientDetailsHeader
                            key={activePatientKey ?? 'idle'}
                            activePatient={headerPatient}
                            queue={headerQueue}
                            isLoadingQueue={isLoading}
                            showSearch={false}
                            queueLabel="Laboratory queue"
                            onSelectPatient={handlePatientSelect}
                            onViewAllPatients={() => setShowQueueModal(true)}
                        />
                        {showQueueModal && (
                            <QueuePatientsModal
                                queue={headerQueue}
                                department="Laboratory"
                                onClose={() => setShowQueueModal(false)}
                                onSelectPatient={handlePatientSelect}
                                onClearQueue={handleClearQueue}
                                isClearing={isClearingQueue}
                            />
                        )}
                    </div>

                    {/* Workbench */}
                    <div data-tour="lab-workbench" className="flex-1 min-h-0 card overflow-hidden flex flex-col z-10 relative">
                        {!activePatientGroup ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-ink-400 bg-ink-50/40 dark:bg-ink-800/40">
                                <FlaskConical size={56} className="mb-4 text-ink-300" strokeWidth={1.5} />
                                <h3 className="text-base font-semibold text-ink-600 dark:text-ink-400 mb-1">Laboratory workbench</h3>
                                <p className="text-sm">Select a patient from the queue to process specimens and enter results.</p>
                            </div>
                        ) : (
                            <>
                                {/* Patient strip + Actions ▾ */}
                                <div className="shrink-0 flex flex-wrap items-center justify-between gap-2 p-3 sm:p-4 border-b border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 z-10">
                                    <div className="flex items-center gap-3 min-w-0">
                                        <div className="size-10 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center ring-1 ring-inset ring-brand-100 shrink-0"><Microscope size={19} /></div>
                                        <div className="min-w-0">
                                            <h1 className="text-base font-semibold text-ink-900 dark:text-ink-100 tracking-tight truncate">{activePatientGroup.patient_name}</h1>
                                            <p className="text-xs font-medium text-ink-500 truncate">{activePatientGroup.outpatient_no || '—'} · {activePatientGroup.tests.length} requested test{activePatientGroup.tests.length === 1 ? '' : 's'}</p>
                                        </div>
                                    </div>
                                    <ActionsMenu has={hasPerm} groups={actionGroups} />
                                </div>

                                {/* Requested-tests rail + results panel */}
                                <div className="flex-1 min-h-0 flex flex-col md:flex-row">
                                    <aside className="md:w-72 shrink-0 border-b md:border-b-0 md:border-r border-ink-100 dark:border-ink-800 bg-ink-50/40 dark:bg-ink-800/30 overflow-y-auto custom-scrollbar max-h-48 md:max-h-none">
                                        <h4 className="px-4 pt-3 pb-2 text-2xs font-semibold uppercase tracking-[0.14em] text-ink-500 dark:text-ink-400 flex items-center gap-2"><ClipboardList size={13} /> Requested tests</h4>
                                        <div className="px-2 pb-2 space-y-1">
                                            {activePatientGroup.tests.map((t) => {
                                                const on = activeTest?.test_id === t.test_id;
                                                return (
                                                    <div key={t.test_id} className={`group relative rounded-xl border transition-colors ${on ? 'bg-brand-50/70 dark:bg-brand-500/10 border-brand-300 dark:border-brand-500/40' : 'bg-white dark:bg-ink-900 border-ink-200 dark:border-ink-800 hover:border-brand-300'}`}>
                                                        <button type="button" onClick={() => loadTest(t)} className="w-full text-left p-3 pr-8">
                                                            <div className="flex items-center gap-2 mb-1">
                                                                <span className="font-medium text-sm text-ink-900 dark:text-ink-100 line-clamp-1">{t.test_name}</span>
                                                                {t.priority === 'STAT' && <AlertCircle size={13} className="text-rose-500 shrink-0" />}
                                                            </div>
                                                            <div className="flex items-center justify-between text-2xs">
                                                                <span className={t.status === 'Pending Collection' ? 'badge-warn' : t.status === 'In Progress' ? 'badge-info' : 'badge-neutral'}>{t.status}</span>
                                                                <span className="text-ink-400 flex items-center gap-1"><Clock size={10} /> {t.requested_at ? new Date(t.requested_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
                                                            </div>
                                                        </button>
                                                        <button type="button" onClick={() => handleCancelTest(t)} title="Remove from queue" aria-label={`Remove ${t.test_name} from the queue`}
                                                            className="absolute top-1.5 right-1.5 p-1 rounded-lg text-ink-300 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-500/10">
                                                            <X size={13} />
                                                        </button>
                                                    </div>
                                                );
                                            })}
                                        </div>
                                    </aside>

                                    {/* Results panel for the selected test */}
                                    <div className="flex-1 min-h-0 flex flex-col">
                                        {!activeTest ? (
                                            <div className="flex-1 flex flex-col items-center justify-center text-ink-400 bg-ink-50/40 dark:bg-ink-800/30 p-6 text-center">
                                                <TestTube size={40} className="mb-3 text-ink-300" strokeWidth={1.5} />
                                                <p className="text-sm">Select a requested test to enter results.</p>
                                            </div>
                                        ) : (
                                            <>
                                                <div className="shrink-0 px-5 py-3 border-b border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex items-center justify-between gap-3 z-10">
                                                    <div className="flex items-center gap-2 min-w-0">
                                                        <h2 className="text-base font-semibold text-ink-900 dark:text-ink-100 tracking-tight truncate">{activeTest.test_name}</h2>
                                                        {activeTest.priority === 'STAT' && <span className="badge-danger animate-pulse-soft">STAT</span>}
                                                        <span className="text-2xs font-mono text-ink-400 shrink-0">#{activeTest.test_id}</span>
                                                    </div>
                                                    {(activeTest.status === 'Completed' || activeTest.result_summary) && (
                                                        <button type="button" onClick={() => printLabReport({
                                                            patient: { full_name: activePatientGroup.patient_name, outpatient_no: activePatientGroup.outpatient_no },
                                                            test: activeTest,
                                                            performedBy: { full_name: activeTest.performed_by_name },
                                                            orderedBy: { full_name: activeTest.doctor } })} className="btn-secondary shrink-0" title="Print lab report">
                                                            <Printer size={15} /> Print report
                                                        </button>
                                                    )}
                                                </div>

                                <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-5 bg-ink-50/40 dark:bg-ink-800/30 custom-scrollbar">

                                    {/* Stage 1: pending collection — only when catalog requires barcode */}
                                    {activeTest.status === 'Pending Collection' ? (
                                        <div className="card p-6 text-center py-12">
                                            <TestTube size={44} className="mx-auto text-ink-300 mb-4" />
                                            <h3 className="text-base font-semibold text-ink-800 dark:text-ink-200 mb-1">Awaiting specimen collection</h3>
                                            <p className="text-sm text-ink-500 mb-6 max-w-md mx-auto">
                                                This test's catalog entry requests a barcode label. You can generate one — or skip
                                                the labelling step entirely if your workflow doesn't need it.
                                            </p>
                                            <div className="flex flex-wrap justify-center gap-3">
                                                <button type="button" onClick={handleRejectSample} className="btn-secondary text-rose-600 border-rose-200 hover:bg-rose-50">
                                                    <XCircle size={16} /> Reject / no-show
                                                </button>
                                                <button type="button" onClick={handleSkipBarcode} className="btn-secondary">
                                                    Skip barcode
                                                </button>
                                                <button type="button" onClick={handleCollectSpecimen} className="btn-primary">
                                                    <Printer size={16} /> Print barcode &amp; receive
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <>
                                            {/* Discrete result entry — driven by lab_catalog_parameters */}
                                            <div className="card-flush p-5 sm:p-6 animate-fade-in">
                                                <h3 className="section-eyebrow mb-5 border-b border-ink-100 dark:border-ink-800 pb-3 flex items-center gap-2">
                                                    <Activity className="text-brand-600" size={16} /> Enter results
                                                </h3>

                                                {activeParameters.length > 0 ? (
                                                    <div className="space-y-3 overflow-x-auto pb-2">
                                                        <div className="grid grid-cols-12 gap-3 items-center bg-ink-50 dark:bg-ink-900/40 p-3 rounded-xl ring-1 ring-ink-100 text-2xs font-semibold text-ink-500 uppercase tracking-wider min-w-[600px]">
                                                            <div className="col-span-4">Parameter</div>
                                                            <div className="col-span-3">Value</div>
                                                            <div className="col-span-2">Unit</div>
                                                            <div className="col-span-2">Ref. range</div>
                                                            <div className="col-span-1 text-center">Flag</div>
                                                        </div>
                                                        {activeParameters.map(param => (
                                                            <div key={param.parameter_id} className="grid grid-cols-12 gap-3 items-center border-b border-ink-100 dark:border-ink-800 pb-2 min-w-[600px]">
                                                                <div className="col-span-4 font-medium text-sm text-ink-700 dark:text-ink-300">{param.name}</div>
                                                                <div className="col-span-3">
                                                                    {param.value_type === 'choice' && param.choices ? (
                                                                        <select className="input" value={results[param.key] || ''}
                                                                                onChange={(e) => setResults({ ...results, [param.key]: e.target.value })}>
                                                                            <option value="">—</option>
                                                                            {param.choices.split(',').map(c => <option key={c.trim()} value={c.trim()}>{c.trim()}</option>)}
                                                                        </select>
                                                                    ) : (
                                                                        <input type={param.value_type === 'number' ? 'number' : 'text'} step="any"
                                                                               aria-label={param.name}
                                                                               value={results[param.key] || ''}
                                                                               onChange={(e) => setResults({ ...results, [param.key]: e.target.value })}
                                                                               className="input" />
                                                                    )}
                                                                </div>
                                                                <div className="col-span-2 text-sm text-ink-500">{param.unit || '—'}</div>
                                                                <div className="col-span-2 text-xs font-mono text-ink-400">
                                                                    {param.ref_low != null || param.ref_high != null
                                                                        ? `${param.ref_low ?? '–∞'} – ${param.ref_high ?? '+∞'}`
                                                                        : '—'}
                                                                </div>
                                                                <div className="col-span-1 flex justify-center">
                                                                    {param.value_type === 'number' && flagFor(results[param.key], param.ref_low, param.ref_high)}
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <div>
                                                        <label htmlFor="labora-qualitative-result-impression" className="label">Qualitative result / impression</label>
                                                        <textarea id="labora-qualitative-result-impression" rows="4" value={results.qualitative || ''}
                                                                  onChange={(e) => setResults({ qualitative: e.target.value })}
                                                                  className="input resize-none"
                                                                  placeholder="Enter findings… (no discrete parameters configured for this test — edit the catalog to add them)" />
                                                    </div>
                                                )}

                                                <div className="mt-4">
                                                    <label htmlFor="labora-technician-notes-optional" className="label">Technician notes (optional)</label>
                                                    <input id="labora-technician-notes-optional" type="text" value={techNotes} onChange={(e) => setTechNotes(e.target.value)} className="input" placeholder="Methodology notes…" />
                                                </div>
                                            </div>

                                            {/* Reagent picker */}
                                            <div className="card-flush p-5 sm:p-6 border-l-4 border-l-amber-400">
                                                <h3 className="section-eyebrow mb-4 border-b border-ink-100 dark:border-ink-800 pb-3 flex items-center gap-2">
                                                    <Package className="text-amber-500" size={16} /> Reagents &amp; consumables used
                                                </h3>

                                                <div className="flex flex-wrap gap-2 mb-4">
                                                    <select value={selectedBatchId} onChange={(e) => setSelectedBatchId(e.target.value)} className="input flex-1 min-w-[12rem]">
                                                        <option value="">Select item from lab store…</option>
                                                        {labInventory.map(item => (
                                                            <option key={item.batch_id} value={item.batch_id}>
                                                                {item.name}{item.is_reusable ? ' (reusable)' : ''} · Batch {item.batch_no} · {item.stock} {item.unit} avail.
                                                            </option>
                                                        ))}
                                                    </select>
                                                    {selectedBatchId && labInventory.find(i => i.batch_id === parseInt(selectedBatchId))?.is_reusable ? (
                                                        <span className="badge-success flex items-center gap-1 px-3"><RefreshCcw size={12} /> Reusable — no qty</span>
                                                    ) : (
                                                        <input aria-label="Qty" type="number" min="1" placeholder="Qty" value={consumeQty}
                                                               onChange={(e) => setConsumeQty(e.target.value)} className="input w-24" />
                                                    )}
                                                    <button type="button" onClick={addConsumedItem} className="btn bg-ink-800 text-white hover:bg-ink-900">
                                                        <Plus size={15} /> Add
                                                    </button>
                                                </div>

                                                {consumedItems.length > 0 ? (
                                                    <div className="card-flush overflow-x-auto">
                                                        <table className="table-clean min-w-[400px]">
                                                            <thead>
                                                                <tr>
                                                                    <th>Item &amp; batch</th>
                                                                    <th>Used</th>
                                                                    <th aria-label="Actions"></th>
                                                                </tr>
                                                            </thead>
                                                            <tbody>
                                                                {consumedItems.map(item => (
                                                                    <tr key={item.batch_id}>
                                                                        <td className="font-medium text-ink-900 dark:text-ink-100">
                                                                            {item.name} <span className="text-xs text-ink-500">({item.batch_no})</span>
                                                                            {item.is_reusable && <span className="ml-2 badge-success text-2xs">Reusable</span>}
                                                                        </td>
                                                                        <td className="font-semibold">
                                                                            {item.is_reusable ? '1 use (no deduct)' : `${item.quantity} ${item.unit}`}
                                                                        </td>
                                                                        <td className="text-right">
                                                                            <button type="button" onClick={() => removeConsumedItem(item.batch_id)} aria-label="Remove"
                                                                                    className="text-ink-400 hover:text-rose-600"><Trash2 size={15} /></button>
                                                                        </td>
                                                                    </tr>
                                                                ))}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                ) : (
                                                    <p className="text-xs text-ink-400 italic">No consumables logged yet. Reusable items can be added without a quantity.</p>
                                                )}
                                            </div>
                                        </>
                                    )}
                                </div>

                                                {/* Footer */}
                                                {activeTest.status !== 'Pending Collection' && (
                                                    <div className="p-4 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex justify-end gap-2 shrink-0 z-10">
                                                        <button type="button" onClick={handleRejectSample} className="btn-secondary text-rose-600 border-rose-200 hover:bg-rose-50">
                                                            <XCircle size={16} /> Reject sample
                                                        </button>
                                                        <button type="button" onClick={handleReleaseResults} className="btn-success">
                                                            <Send size={16} /> Verify, release &amp; reconcile stock
                                                        </button>
                                                    </div>
                                                )}
                                            </>
                                        )}
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                </>
            )}

            {/* ─────────────── Mode 2: Test Catalog (editable) ─────────────── */}
            {activeTab === 'catalog' && (
                <div className="flex-1 card flex flex-col overflow-hidden">
                    <div className="p-5 border-b border-ink-100 dark:border-ink-800 bg-ink-50/40 flex justify-between items-center flex-wrap gap-3">
                        <div>
                            <span className="section-eyebrow">Admin</span>
                            <h2 className="text-base font-semibold text-ink-900 dark:text-ink-100 mt-1 flex items-center gap-2 tracking-tight">
                                <Settings className="text-ink-400" size={18} /> Managed test directory
                            </h2>
                            <p className="text-sm text-ink-500 mt-1">Add or revise tests, parameters, reference ranges and pricing.</p>
                        </div>
                        <button type="button" data-tour="lab-new-test" onClick={startCreate} className="btn-primary">
                            <Plus size={16} /> New test
                        </button>
                    </div>

                    <div data-tour="lab-catalog" className="flex-1 overflow-auto">
                        <table className="table-clean min-w-[700px]">
                            <thead>
                                <tr>
                                    <th>Test</th>
                                    <th>Category</th>
                                    <th>Specimen</th>
                                    <th>Parameters</th>
                                    <th>Price</th>
                                    <th>Barcode</th>
                                    <th>Status</th>
                                    <th className="text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {isLoading ? (
                                    <tr><td colSpan="8" className="text-center py-8 text-ink-400">Loading catalog…</td></tr>
                                ) : catalog.length === 0 ? (
                                    <tr><td colSpan="8" className="text-center py-8 text-ink-500">No laboratory tests configured yet. Click "New test" to add one.</td></tr>
                                ) : catalog.map((test) => (
                                    <tr key={test.catalog_id} className={!test.is_active ? 'opacity-50' : ''}>
                                        <td>
                                            <div className="font-semibold text-ink-900 dark:text-ink-100">{test.test_name}</div>
                                            <div className="text-xs font-mono text-ink-500 mt-0.5">PKG-LAB-{String(test.catalog_id).padStart(4, '0')}</div>
                                        </td>
                                        <td className="font-medium text-ink-700 dark:text-ink-300">{test.category}</td>
                                        <td><span className="badge-neutral">{test.default_specimen_type || 'General'}</span></td>
                                        <td className="text-xs text-ink-600 dark:text-ink-400">{(test.parameters || []).length} field(s)</td>
                                        <td className="font-mono">{Number(test.base_price).toFixed(2)}</td>
                                        <td>{test.requires_barcode ? <span className="badge-warn text-2xs">Required</span> : <span className="badge-neutral text-2xs">Optional</span>}</td>
                                        <td>{test.is_active ? <span className="badge-success text-2xs">Active</span> : <span className="badge-neutral text-2xs">Inactive</span>}</td>
                                        <td className="text-right">
                                            <button type="button" onClick={() => startEdit(test)} className="text-brand-600 hover:text-brand-800 p-1.5" aria-label="Edit"><Pencil size={15} /></button>
                                            {test.is_active && (
                                                <button type="button" onClick={() => deactivateCatalog(test)} className="text-rose-600 hover:text-rose-800 p-1.5 ml-1" aria-label="Deactivate"><Trash2 size={15} /></button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {/* ─────────────── Catalog editor drawer ─────────────── */}
            {editorOpen && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setEditorOpen(false)} />
                    <div className="relative w-full max-w-3xl bg-white dark:bg-ink-900 h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="flex items-center justify-between p-5 border-b border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 shrink-0">
                            <div>
                                <span className="section-eyebrow">{editing ? 'Edit test' : 'New test'}</span>
                                <h2 className="text-xl font-semibold text-ink-900 dark:text-ink-100 mt-1 flex items-center gap-2">
                                    <FlaskConical size={20} className="text-brand-600" />
                                    {editing ? `Editing ${editing.test_name}` : 'Configure a new lab test'}
                                </h2>
                            </div>
                            <button type="button" onClick={() => setEditorOpen(false)} aria-label="Close" className="text-ink-400 hover:text-ink-700 p-2 hover:bg-ink-100 dark:hover:bg-ink-800 rounded-full">
                                <X size={20} />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 bg-ink-50/60 custom-scrollbar space-y-5">
                            <div className="card p-5 space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div>
                                        <label htmlFor="labora-test-name" className="label">Test name *</label>
                                        <input id="labora-test-name" className="input" value={catalogForm.test_name}
                                               onChange={e => setCatalogForm({ ...catalogForm, test_name: e.target.value })} />
                                    </div>
                                    <div>
                                        <label htmlFor="labora-category" className="label">Category *</label>
                                        <input id="labora-category" className="input" value={catalogForm.category}
                                               onChange={e => setCatalogForm({ ...catalogForm, category: e.target.value })}
                                               placeholder="Hematology, Biochemistry…" />
                                    </div>
                                    <div>
                                        <label htmlFor="labora-default-specimen" className="label">Default specimen</label>
                                        <input id="labora-default-specimen" className="input" value={catalogForm.default_specimen_type}
                                               onChange={e => setCatalogForm({ ...catalogForm, default_specimen_type: e.target.value })} />
                                    </div>
                                    <div>
                                        <label htmlFor="labora-base-price" className="label">Base price</label>
                                        <input id="labora-base-price" type="number" min="0" step="0.01" className="input" value={catalogForm.base_price}
                                               onChange={e => setCatalogForm({ ...catalogForm, base_price: e.target.value })} />
                                    </div>
                                    <div>
                                        <label htmlFor="labora-turnaround-hours" className="label">Turnaround (hours)</label>
                                        <input id="labora-turnaround-hours" type="number" min="0" className="input" value={catalogForm.turnaround_hours}
                                               onChange={e => setCatalogForm({ ...catalogForm, turnaround_hours: e.target.value })} />
                                    </div>
                                    <div className="flex items-center gap-6 mt-6 md:mt-7">
                                        <label className="flex items-center gap-2 text-sm">
                                            <input type="checkbox" checked={catalogForm.is_active}
                                                   onChange={e => setCatalogForm({ ...catalogForm, is_active: e.target.checked })} />
                                            Active
                                        </label>
                                        <label className="flex items-center gap-2 text-sm">
                                            <input type="checkbox" checked={catalogForm.requires_barcode}
                                                   onChange={e => setCatalogForm({ ...catalogForm, requires_barcode: e.target.checked })} />
                                            Requires barcode
                                        </label>
                                    </div>
                                </div>
                                <div>
                                    <label htmlFor="labora-description" className="label">Description</label>
                                    <textarea id="labora-description" rows="2" className="input resize-none" value={catalogForm.description || ''}
                                              onChange={e => setCatalogForm({ ...catalogForm, description: e.target.value })} />
                                </div>
                            </div>

                            <div className="card p-5">
                                <div className="flex items-center justify-between mb-3">
                                    <h3 className="font-semibold text-ink-900 dark:text-ink-100">Result parameters</h3>
                                    <button type="button" onClick={addParamRow} className="btn-secondary"><Plus size={14} /> Add parameter</button>
                                </div>
                                {catalogForm.parameters.length === 0 ? (
                                    <p className="text-xs text-ink-500 italic">No parameters yet. Without any, the lab tech enters a single free-text result.</p>
                                ) : (
                                    <div className="space-y-2">
                                        {catalogForm.parameters.map((p, idx) => (
                                            <div key={p._uid} className="grid grid-cols-12 gap-2 items-start border-b border-ink-100 dark:border-ink-800 pb-2">
                                                <input aria-label="key" className="input col-span-2" placeholder="key" value={p.key}
                                                       onChange={e => setParamField(idx, 'key', e.target.value)} />
                                                <input aria-label="Display name" className="input col-span-3" placeholder="Display name" value={p.name}
                                                       onChange={e => setParamField(idx, 'name', e.target.value)} />
                                                <input aria-label="Unit" className="input col-span-1" placeholder="Unit" value={p.unit || ''}
                                                       onChange={e => setParamField(idx, 'unit', e.target.value)} />
                                                <select className="input col-span-2" value={p.value_type}
                                                        onChange={e => setParamField(idx, 'value_type', e.target.value)}>
                                                    <option value="number">number</option>
                                                    <option value="text">text</option>
                                                    <option value="choice">choice</option>
                                                </select>
                                                <input aria-label="min" className="input col-span-1" placeholder="min" value={p.ref_low ?? ''}
                                                       onChange={e => setParamField(idx, 'ref_low', e.target.value)} />
                                                <input aria-label="max" className="input col-span-1" placeholder="max" value={p.ref_high ?? ''}
                                                       onChange={e => setParamField(idx, 'ref_high', e.target.value)} />
                                                <button type="button" onClick={() => removeParamRow(idx)} className="col-span-2 btn-secondary text-rose-600 border-rose-200 hover:bg-rose-50">
                                                    <Trash2 size={14} /> Remove
                                                </button>
                                                {p.value_type === 'choice' && (
                                                    <input aria-label="comma-separated choices (e.g. Positive, Negative, Inconclusive)" className="input col-span-12" placeholder="comma-separated choices (e.g. Positive, Negative, Inconclusive)"
                                                           value={p.choices || ''} onChange={e => setParamField(idx, 'choices', e.target.value)} />
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="p-4 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex justify-end gap-2 shrink-0">
                            <button type="button" onClick={() => setEditorOpen(false)} className="btn-secondary">Cancel</button>
                            <button type="button" onClick={saveCatalog} className="btn-primary"><Save size={15} /> Save</button>
                        </div>
                    </div>
                </div>
            )}

            {/* Consolidated Actions ▾ surfaces */}
            {activePatientGroup && actionModal === 'files' && (
                <FilesModal patient={{ patient_id: activePatientGroup.patient_id, patient_name: activePatientGroup.patient_name }}
                    recordId={null} onClose={() => setActionModal(null)} />
            )}
            {actionModal === 'queue' && (
                <QueuePatientModal onQueued={fetchLaboratoryData} onClose={() => setActionModal(null)} />
            )}
            {activePatientGroup && historyModal && (
                <PatientHistoryModal
                    patientId={activePatientGroup.patient_id}
                    initialSection={historyModal.entry_type}
                    onClose={() => setHistoryModal(null)}
                />
            )}
        </div>
    );
}
