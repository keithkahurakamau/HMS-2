import React, { useState, useEffect, useRef } from 'react';
import {} from 'react-router-dom';
import { apiClient } from '../api/client';
import { newIdempotencyKey } from '../api/mpesa';
import {
    Search, Pill, CheckCircle2, AlertCircle,
    Printer, XCircle, Stethoscope,
    ShoppingCart, Plus, Minus, Trash2, CreditCard, Store, Activity,
    Banknote, Smartphone, X as XIcon, ReceiptText, History,
    Wallet, Paperclip, FileText, UserPlus, RotateCcw } from 'lucide-react';
import toast from 'react-hot-toast';
import { printPrescription } from '../utils/printTemplates';
import { printDocument, printUtils } from '../utils/printDocument';
import { printVisitSummary, printLabReport } from '../utils/printReports';
import PageHeader from '../components/PageHeader';
import QueuePatientsModal from '../components/QueuePatientsModal';
import MpesaStkProgress from '../components/MpesaStkProgress';
import usePaymentSocket from '../hooks/usePaymentSocket';
import { useAuth } from '../context/AuthContext';
import PatientDetailsHeader from './clinical/PatientDetailsHeader';
import DepartmentQueue from '../components/DepartmentQueue';
import ActionsMenu from './clinical/ActionsMenu';
import FilesModal from './clinical/modals/FilesModal';
import QueuePatientModal from './clinical/modals/QueuePatientModal';

// Pure helper hoisted to module scope (no component state).
const genKey = () => crypto.randomUUID();

export default function Pharmacy() {
    const auth = useAuth();
    const perms = auth?.user?.permissions || [];
    const hasPerm = (p) => perms.includes(p);

    // --- APP STATE ---
    const [activeTab, setActiveTab] = useState('rx'); // 'rx' | 'otc' | 'transactions'
    const [isLoading, setIsLoading] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);

    // --- RX FULFILLMENT STATE (DYNAMIC) ---
    const [queue, setQueue] = useState([]);
    const [isLoadingQueue, setIsLoadingQueue] = useState(true);
    const [activeOrder, setActiveOrder] = useState(null);
    // Per-line "packed" toggles and dispense quantities for the active order,
    // both keyed by line index.
    const [packed, setPacked] = useState({});
    const [lineQty, setLineQty] = useState({});
    // Consolidated Actions ▾ / secondary surfaces.
    const [actionModal, setActionModal] = useState(null); // 'files' | 'queue' | null

    // --- OTC POINT OF SALE STATE (RETAIL) ---
    const [otcSearch, setOtcSearch] = useState('');
    const [inventory, setInventory] = useState([]);
    const [cart, setCart] = useState([]);

    // --- PAYMENT MODAL STATE (post-dispense) ---
    // payment.invoice_id is the rolled-up invoice for the dispense run;
    // payment.lastDispenseId is the dispense whose /pay endpoint we'll hit
    // (any of the items work, they share the invoice).
    const [payment, setPayment] = useState(null);

    // --- DATA FETCHING ---
    useEffect(() => {
        fetchPharmacyInventory();
        fetchRxQueue();
    }, []);

    const fetchPharmacyInventory = async () => {
        setIsLoading(true);
        try {
            const response = await apiClient.get('/pharmacy/inventory');
            setInventory(response.data || []);
        } catch (error) {
            toast.error("Failed to load pharmacy inventory.");
        } finally {
            setIsLoading(false);
        }
    };

    // "View all patients" opens the full queue in place. It used to navigate to
    // the registry, which lost the clinician's place in the workspace and did
    // not actually show who was waiting.
    const [showQueueModal, setShowQueueModal] = useState(false);
    const [isClearingQueue, setIsClearingQueue] = useState(false);

    const handleClearQueue = async () => {
        setIsClearingQueue(true);
        try {
            const res = await apiClient.post('/queue/end-of-day', { department: 'Pharmacy' });
            const n = res.data?.checked_out ?? 0;
            toast.success(n > 0
                ? `${n} patient(s) removed from the queue.`
                : 'The queue was already empty.');
            setShowQueueModal(false);
            
            fetchRxQueue();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Could not clear the queue.');
        } finally {
            setIsClearingQueue(false);
        }
    };

    const fetchRxQueue = async () => {
        setIsLoadingQueue(true);
        try {
            const response = await apiClient.get('/clinical/prescriptions/pending');
            setQueue(response.data || []);
        } catch (error) {
            // Silently handle if route doesn't exist yet during our build phase
            console.warn("Prescription queue endpoint not yet available.");
        } finally {
            setIsLoadingQueue(false);
        }
    };

    // The dispense queue is a list of prescription orders; map each to the
    // shape the shared PatientDetailsHeader renders (Q.No · OPD · Name · From ·
    // Mins). `queue_id` doubles as the row identity + active-row highlight key.
    const headerQueue = queue.map((o) => ({
        ...o,
        queue_id: o.id,
        patient_name: o.patient,
        outpatient_no: o.op_no,
        triage_time: o.time,
        priority: o.priority === 'High' ? 'High' : 'Normal' }));
    const headerPatient = activeOrder ? {
        patient_name: activeOrder.patient,
        outpatient_no: activeOrder.op_no,
        age: activeOrder.age,
        gender: activeOrder.gender,
        allergies: activeOrder.allergies,
        queue_id: activeOrder.id } : null;

    const selectOrder = (order) => {
        setActiveOrder(order);
        setPacked({});
        setLineQty({});
    };
    const clearActiveOrder = () => { setActiveOrder(null); setPacked({}); setLineQty({}); };
    const togglePacked = (idx) => setPacked((p) => ({ ...p, [idx]: !p[idx] }));
    const setQty = (idx, v) => setLineQty((q) => ({ ...q, [idx]: v }));

    const rxLines = activeOrder?.prescriptions || [];

    // Resolve each prescription line to a stock batch by name (loose two-way
    // contains match), preferring an in-stock batch. Prescriptions carry no
    // batch/price, so this bridges them to dispensable stock; the pharmacist
    // confirms the quantity per line and sees the matched batch before packing.
    const resolveBatch = (drug) => {
        const n = (drug || '').toLowerCase().trim();
        if (!n) return null;
        const match = (it) => { const a = (it.name || '').toLowerCase(); return a.includes(n) || n.includes(a); };
        return inventory.find((it) => it.quantity > 0 && match(it)) || inventory.find(match) || null;
    };

    // One pass over the prescription lines derives everything the bill needs:
    // the display rows (line + matched batch + qty + amount) plus, by side
    // effect, the running total, the packed-line count, and the dispense run
    // (packed lines with a resolved batch and a quantity).
    let rxTotal = 0;
    let packedCount = 0;
    const rxCart = [];
    const lineRows = rxLines.map((line, idx) => {
        const batch = resolveBatch(line.drug);
        const qty = Number(lineQty[idx] || 0);
        const amount = batch && qty > 0 ? Number(batch.unit_price) * qty : 0;
        rxTotal += amount;
        if (packed[idx]) {
            packedCount += 1;
            if (batch && qty > 0) rxCart.push({ batch_id: batch.batch_id, qty, notes: line.drug });
        }
        return { line, idx, batch, qty, amount };
    });

    const filteredInventory = inventory.filter(item =>
        item.name.toLowerCase().includes(otcSearch.toLowerCase()) || 
        item.category.toLowerCase().includes(otcSearch.toLowerCase())
    );

    // --- CART LOGIC (OTC) ---
    const addToCart = (item) => {
        if (item.quantity === 0) return toast.error("Item is out of stock!");
        const existing = cart.find(c => c.batch_id === item.batch_id);
        
        if (existing) {
            if (existing.qty >= item.quantity) return toast.error("Cannot exceed available batch stock!");
            setCart(cart.map(c => c.batch_id === item.batch_id ? { ...c, qty: c.qty + 1 } : c));
        } else {
            setCart([...cart, { ...item, qty: 1 }]);
        }
    };
    
    const updateQty = (batch_id, delta) => {
        setCart(cart.map(c => {
            if (c.batch_id === batch_id) {
                const newQty = c.qty + delta;
                return newQty > 0 ? { ...c, qty: newQty } : c;
            }
            return c;
        }));
    };

    const removeFromCart = (batch_id) => setCart(cart.filter(c => c.batch_id !== batch_id));
    const cartTotal = cart.reduce((sum, item) => sum + (item.unit_price * item.qty), 0);

    // --- API SUBMISSION HANDLERS ---
    // crypto.randomUUID() is collision-resistant; the prior Math.random
    // construction could repeat under load and let a double-click look like
    // a single idempotent retry on the server side.
    // Loops the cart and posts one /pharmacy/dispense call per line.
    // Returns the array of API responses (each carries invoice_id +
    // invoice_balance when the patient is known).
    const dispenseItems = async (items, { patient_id = null, record_id = null } = {}) => {
        const responses = [];
        for (const it of items) {
            const res = await apiClient.post('/pharmacy/dispense', {
                idempotency_key: genKey(),
                batch_id: it.batch_id,
                quantity: it.qty,
                patient_id,
                record_id,
                notes: it.notes || null });
            responses.push(res.data);
        }
        return responses;
    };

    // Pay-straight-away OTC checkout: dispense the cart, then immediately
    // process the chosen method against the rolled-up invoice. No "choose
    // method" modal: the cashier already picked Cash/Card/M-Pesa.
    const handleOTCPay = async (method, { phoneNumber = null, reference = null } = {}) => {
        if (cart.length === 0) return;
        if (method === 'mpesa' && !phoneNumber) {
            return toast.error('M-Pesa needs a phone number.');
        }
        setIsProcessing(true);
        try {
            const responses = await dispenseItems(cart);  // walk-in
            fetchPharmacyInventory();

            const last = responses[responses.length - 1];
            if (!last?.invoice_id) {
                setCart([]);
                toast.success('Items dispensed (no invoice).');
                return;
            }

            const amount = Number(last.invoice_balance ?? cartTotal);
            const res = await apiClient.post(`/pharmacy/dispense/${last.dispense_id}/pay`, {
                method,
                amount,
                phone_number: method === 'mpesa' ? phoneNumber : null,
                transaction_reference: reference || null,
                idempotency_key: method === 'mpesa' ? newIdempotencyKey() : null,
            });

            if (method === 'mpesa') {
                toast.success('STK push sent. Customer to confirm on their phone.');
                // Open the modal in polling mode so the cashier can watch.
                setPayment({
                    invoiceId: last.invoice_id,
                    dispenseId: last.dispense_id,
                    amount,
                    patientName: 'Walk-in',
                    pendingMpesa: { external_reference: res.data?.external_reference,
                                    checkout_request_id: res.data?.checkout_request_id,
                                    transaction_id: res.data?.transaction_id,
                                    phone: phoneNumber } });
            } else {
                toast.success(`${method === 'card' ? 'Card' : 'Cash'} payment recorded.`);
                // Receipt prints directly without the modal round-trip.
                try {
                    const r = await apiClient.get(`/pharmacy/dispense/${last.dispense_id}/receipt`);
                    printPharmacyReceipt(r.data);
                } catch { /* silently skip, payment still landed */ }
                setCart([]);
            }
        } catch (error) {
            toast.error(error?.response?.data?.detail || `${method} payment failed.`);
        } finally {
            setIsProcessing(false);
        }
    };

    const handleReturnToDoctor = async () => {
        if (!activeOrder?.record_id) return;
        const reason = window.prompt(
            'Why is this prescription being returned to the doctor? (e.g. dose ambiguity, drug-drug interaction)'
        );
        if (!reason) return;
        try {
            await apiClient.post(`/clinical/prescriptions/${activeOrder.record_id}/return`, { reason });
            toast.success('Returned to doctor with reason.');
            setQueue(queue.filter(q => q.id !== activeOrder.id));
            clearActiveOrder();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Return failed.');
        }
    };

    const cancelPrescription = async (recordId) => {
        const reason = window.prompt('Reason for cancelling this prescription:') ?? null;
        if (reason === null) return;
        try {
            await apiClient.post(`/clinical/prescriptions/${recordId}/cancel`, { reason });
            toast.success('Prescription cancelled.');
            fetchRxQueue();
            clearActiveOrder();
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not cancel prescription.');
        }
    };

    const handleRxDispense = async () => {
        if (!activeOrder) return;
        if (rxCart.length === 0) {
            return toast.error('Set a quantity and mark at least one in-stock line as packed first.');
        }
        setIsProcessing(true);
        try {
            const responses = await dispenseItems(rxCart, {
                patient_id: activeOrder.patient_id,
                record_id: activeOrder.record_id });
            toast.success(`Prescription ${activeOrder.id} dispensed.`);
            fetchPharmacyInventory();

            // Open payment modal seeded from the rolled-up invoice.
            const last = responses[responses.length - 1];
            if (last?.invoice_id) {
                setPayment({
                    invoiceId: last.invoice_id,
                    dispenseId: last.dispense_id,
                    amount: last.invoice_balance ?? rxTotal,
                    patientName: activeOrder.patient });
            } else {
                // No invoice (walk-in): just clear and exit.
                setCart([]);
                setQueue(queue.filter(q => q.id !== activeOrder.id));
                clearActiveOrder();
            }
        } catch (error) {
            toast.error(error?.response?.data?.detail || "Failed to dispense prescription.");
        } finally {
            setIsProcessing(false);
        }
    };

    const handlePaymentSettled = async (settledPayment) => {
        // Called by the modal when payment completes successfully.
        // Fire the receipt print before we tear down state, the modal's
        // already closed by the time this resolves.
        const dispenseId = settledPayment?.dispenseId ?? payment?.dispenseId;
        if (dispenseId) {
            try {
                const r = await apiClient.get(`/pharmacy/dispense/${dispenseId}/receipt`);
                printPharmacyReceipt(r.data);
            } catch {
                toast.error("Could not load receipt for printing.");
            }
        }
        setPayment(null);
        setCart([]);
        if (activeOrder) {
            setQueue(queue.filter(q => q.id !== activeOrder.id));
            clearActiveOrder();
        }
    };

    // Prescription report == the printable Rx (mirrors MedicentreV3's Actions).
    const handlePrintRx = () => {
        if (!activeOrder) return;
        printPrescription({
            patient: { full_name: activeOrder.patient, outpatient_no: activeOrder.op_no, allergies: activeOrder.allergies },
            doctor: { full_name: activeOrder.doctor, license_number: activeOrder.doctor_license },
            items: rxLines.map((p) => ({ drug_name: p.drug, formulation: p.formulation, dosage: p.dosage, frequency: p.frequency, duration: p.duration, route: p.route || p.notes })),
            notes: activeOrder.clinical_notes,
            recordId: activeOrder.id });
    };

    // Visit summary: printed from what the pharmacy can see of the encounter.
    const handleVisitSummary = () => {
        if (!activeOrder) return;
        printVisitSummary({
            patient: { full_name: activeOrder.patient, outpatient_no: activeOrder.op_no, allergies: activeOrder.allergies },
            encounter: {
                date: new Date(),
                doctorName: activeOrder.doctor,
                medications: rxLines.map((p) => ({ drug_name: p.drug, dosage: p.dosage, frequency: p.frequency, duration: p.duration })),
                hpi: activeOrder.clinical_notes } });
    };

    // Lab report: pull the patient's tests then print (shared printLabReport).
    const handleLabReport = () => {
        if (!activeOrder?.patient_id) return;
        apiClient.get('/laboratory/tests', { params: { patient_id: activeOrder.patient_id } })
            .then((r) => printLabReport({ patient: { full_name: activeOrder.patient, outpatient_no: activeOrder.op_no }, tests: r.data || [] }))
            .catch((e) => toast.error(e.response?.data?.detail || 'Could not load lab tests.'));
    };

    // Consolidated Actions ▾, mirrors MedicentreV3's Pharmacy menu; permission-
    // gated (empty groups disappear).
    const actionGroups = [
        { label: 'Flow', items: [
            { label: 'Return to doctor', icon: RotateCcw, perm: 'pharmacy:manage', onClick: handleReturnToDoctor },
            { label: 'Cancel script', icon: XCircle, perm: 'pharmacy:manage', onClick: () => cancelPrescription(activeOrder?.record_id) },
            { label: 'Queue Patient', icon: UserPlus, perm: 'patients:write', onClick: () => setActionModal('queue') },
        ] },
        { label: 'Documents', items: [
            { label: 'Attachments', icon: Paperclip, perm: 'clinical:read', onClick: () => setActionModal('files') },
        ] },
        { label: 'Reports', items: [
            { label: 'Prescription Report', icon: Printer, onClick: handlePrintRx },
            { label: 'Visit Summary', icon: FileText, onClick: handleVisitSummary },
            { label: 'Lab Report', icon: FileText, perm: 'laboratory:read', onClick: handleLabReport },
        ] },
    ];

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">
            <PageHeader
                eyebrow="Dispensary"
                icon={Pill}
                title="Pharmacy"
                subtitle="Fulfil prescriptions, dispense over-the-counter sales, and track stock movements."
            />
            {/* GLOBAL PHARMACY HEADER & TABS */}
            <div data-tour="pharmacy-tabs" className="card p-2 flex flex-col sm:flex-row items-stretch sm:items-center justify-between shrink-0 gap-2">
                <div role="tablist" aria-label="Pharmacy mode" className="segmented max-w-md">
                    <button type="button" role="tab" aria-selected={activeTab === 'rx'} onClick={() => setActiveTab('rx')} className={`segmented-option ${activeTab === 'rx' ? 'segmented-option-active' : ''}`}>
                        <Pill size={16} className={activeTab === 'rx' ? 'text-brand-600 dark:text-brand-400' : 'text-ink-400'} /> Rx Fulfillment
                    </button>
                    <button type="button" role="tab" aria-selected={activeTab === 'otc'} onClick={() => setActiveTab('otc')} className={`segmented-option ${activeTab === 'otc' ? 'segmented-option-active' : ''}`}>
                        <Store size={16} className={activeTab === 'otc' ? 'text-accent-600 dark:text-accent-400' : 'text-ink-400'} /> OTC Point of Sale
                    </button>
                    <button type="button" role="tab" aria-selected={activeTab === 'transactions'} onClick={() => setActiveTab('transactions')} className={`segmented-option ${activeTab === 'transactions' ? 'segmented-option-active' : ''}`}>
                        <History size={16} className={activeTab === 'transactions' ? 'text-brand-600 dark:text-brand-400' : 'text-ink-400'} /> Transactions
                    </button>
                </div>
                <div className="text-right px-3 text-xs font-semibold text-ink-500">
                    {/* react-doctor-disable-next-line react-doctor/rendering-hydration-mismatch-time */}
                    {new Date().toLocaleDateString('en-KE', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                </div>
            </div>

            {/* ========================================= */}
            {/* MODE 1: PRESCRIPTION FULFILLMENT (CLINICAL) */}
            {/* ========================================= */}
            {activeTab === 'rx' && (
                <>
                    {/* Patients routed here via the shared queue (walk-ins sent to Pharmacy) */}
                    <DepartmentQueue department="Pharmacy" inline onChange={fetchRxQueue} />
                    {/* Patient details + dispense queue (shared DoctorV2 header) */}
                    <div data-tour="pharmacy-dispense-queue" className="shrink-0 z-20">
                        <PatientDetailsHeader
                            key={activeOrder?.id ?? 'idle'}
                            activePatient={headerPatient}
                            queue={headerQueue}
                            isLoadingQueue={isLoadingQueue}
                            showSearch={false}
                            queueLabel="Pharmacy queue"
                            onSelectPatient={(item) => { if (item?.patient_name) selectOrder(item); }}
                            onRemoveFromQueue={(item) => item.record_id && cancelPrescription(item.record_id)}
                            onViewAllPatients={() => setShowQueueModal(true)}
                        />
                        {showQueueModal && (
                            <QueuePatientsModal
                                queue={headerQueue}
                                department="Pharmacy"
                                onClose={() => setShowQueueModal(false)}
                                onSelectPatient={(item) => { if (item?.patient_name) selectOrder(item); }}
                                onRemoveFromQueue={(item) => item.record_id && cancelPrescription(item.record_id)}
                                onClearQueue={handleClearQueue}
                                isClearing={isClearingQueue}
                            />
                        )}
                    </div>

                    {/* Dispense workspace */}
                    <div className="flex-1 min-h-0 card overflow-hidden flex flex-col z-10 relative">
                        {!activeOrder ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-ink-400 bg-ink-50/40 dark:bg-ink-800/40">
                                <Pill size={56} className="mb-4 text-ink-300" strokeWidth={1.5} />
                                <h3 className="text-base font-semibold text-ink-600 dark:text-ink-400 mb-1">Select a prescription</h3>
                                <p className="text-sm">Choose a patient from the queue to dispense.</p>
                            </div>
                        ) : (
                            <>
                                {/* Rx header strip + Actions ▾ */}
                                <div className="shrink-0 flex flex-wrap items-center justify-between gap-2 p-3 sm:p-4 border-b border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 z-10">
                                    <div className="flex items-center gap-3 min-w-0">
                                        <div className="size-10 rounded-full bg-gradient-to-br from-brand-400 to-accent-500 text-white flex items-center justify-center shadow-glow shrink-0"><Pill size={17} /></div>
                                        <div className="min-w-0">
                                            <h1 className="text-base font-semibold text-ink-900 dark:text-ink-100 tracking-tight truncate">Bill · {activeOrder.id}</h1>
                                            <p className="text-xs font-medium text-ink-500 truncate">{activeOrder.doctor} &middot; {activeOrder.time}</p>
                                        </div>
                                    </div>
                                    <ActionsMenu has={hasPerm} groups={actionGroups} />
                                </div>

                                {/* Scroll body: bill payment details + bill items */}
                                <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4 bg-ink-50/40 dark:bg-ink-800/30 custom-scrollbar">
                                    <BillPaymentDetails total={rxTotal} />
                                    <BillItemsTable rows={lineRows} packed={packed} onToggle={togglePacked} onQty={setQty} />
                                </div>

                                {/* Footer: packed progress + dispense */}
                                <div data-tour="pharmacy-rx-actions" className="shrink-0 p-4 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex flex-wrap items-center justify-between gap-3 z-10">
                                    <p className="text-xs text-ink-500 dark:text-ink-400 flex items-center gap-1.5">
                                        <Stethoscope size={13} /> {packedCount}/{rxLines.length} lines packed &middot; Bill {fmtKES(rxTotal)}
                                    </p>
                                    <div className="flex items-center gap-2">
                                        <button type="button" onClick={handlePrintRx} className="btn-secondary">
                                            <Printer size={15} /> Print Rx
                                        </button>
                                        <button type="button" onClick={handleRxDispense} disabled={isProcessing || rxCart.length === 0} className="btn-primary">
                                            <CheckCircle2 size={16} /> {isProcessing ? 'Processing…' : 'Dispense & bill'}
                                        </button>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                </>
            )}

            {/* ========================================= */}
            {/* MODE 2: OTC POINT OF SALE (RETAIL)        */}
            {/* ========================================= */}
            {activeTab === 'otc' && (
                <div className="flex-1 flex flex-col md:flex-row gap-4 overflow-hidden">
                    {/* LEFT PANEL: INVENTORY SEARCH */}
                    <div data-tour="pharmacy-otc-search" className="flex-1 card flex flex-col overflow-hidden">
                        <div className="p-4 border-b border-ink-100 dark:border-ink-800 bg-ink-50/40">
                            <div className="relative">
                                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                                <input aria-label="Search pharmacy inventory…"
                                    type="text"
                                    placeholder="Search pharmacy inventory…"
                                    value={otcSearch}
                                    onChange={(e) => setOtcSearch(e.target.value)}
                                    className="input pl-10"
                                />
                            </div>
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                            {isLoading ? (
                                <div className="h-full flex flex-col items-center justify-center text-ink-400">
                                    <Activity className="animate-spin mb-2" size={20} /> Loading local batches&hellip;
                                </div>
                            ) : filteredInventory.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center text-ink-400">No stock matches your search.</div>
                            ) : (
                                <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                                    {filteredInventory.map(item => (
                                        <div key={item.batch_id} className="border border-ink-200 dark:border-ink-800 rounded-xl p-3 hover:border-accent-300 transition-all bg-white dark:bg-ink-900 flex flex-col justify-between">
                                            <div>
                                                <div className="flex justify-between items-start mb-1 gap-2">
                                                    <h4 className="font-semibold text-sm text-ink-900 dark:text-ink-100">{item.name}</h4>
                                                    <span className="badge-neutral">{item.category}</span>
                                                </div>
                                                <div className="flex items-center gap-2 mt-2">
                                                    <span className="font-semibold text-accent-700">KES {item.unit_price}</span>
                                                    <span className="text-ink-300">·</span>
                                                    <span className={`text-xs font-medium ${item.quantity > 0 ? 'text-ink-500' : 'text-rose-600'}`}>Stock: {item.quantity}</span>
                                                </div>
                                                <div className="text-2xs text-ink-400 mt-1 uppercase tracking-wider font-mono">Batch: {item.batch_number}</div>
                                            </div>
                                            <button type="button"
                                                onClick={() => addToCart(item)}
                                                disabled={item.quantity === 0}
                                                aria-label={`Add ${item.name} (batch ${item.batch_number}) to cart`}
                                                className="mt-3 w-full py-1.5 bg-ink-50 dark:bg-ink-900/40 border border-ink-200 dark:border-ink-800 hover:bg-accent-50 hover:border-accent-300 hover:text-accent-700 text-ink-700 dark:text-ink-300 text-sm font-semibold rounded-lg flex items-center justify-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                            >
                                                <Plus size={14} /> Add
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* RIGHT PANEL: SHOPPING CART */}
                    <div className="w-full md:w-96 card flex flex-col overflow-hidden shrink-0">
                        <div className="p-4 border-b border-ink-100 dark:border-ink-800 bg-ink-50/40 flex justify-between items-center">
                            <h3 className="font-semibold text-ink-900 dark:text-ink-100 flex items-center gap-2 tracking-tight">
                                <ShoppingCart size={16} className="text-accent-600" /> Current sale
                            </h3>
                            <span className="badge-success">{cart.length} Items</span>
                        </div>

                        <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar bg-ink-50/20">
                            {cart.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center text-ink-400 space-y-2">
                                    <ShoppingCart size={40} className="opacity-30" />
                                    <p className="text-sm">Cart is empty</p>
                                </div>
                            ) : (
                                cart.map(item => (
                                    <div key={item.batch_id} className="card-flush p-3">
                                        <div className="flex justify-between items-start mb-2 gap-2">
                                            <h4 className="font-semibold text-sm text-ink-800 dark:text-ink-200 line-clamp-1">{item.name}</h4>
                                            <button type="button" onClick={() => removeFromCart(item.batch_id)} aria-label="Remove" className="text-ink-400 hover:text-rose-600 transition-colors p-0.5"><Trash2 size={15} /></button>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-xs font-medium text-ink-500">KES {item.unit_price} &times; {item.qty}</span>
                                            <div className="flex items-center gap-1 bg-ink-50 dark:bg-ink-900/40 border border-ink-200 dark:border-ink-800 rounded-lg p-0.5">
                                                <button type="button" onClick={() => updateQty(item.batch_id, -1)} aria-label="Decrease" className="p-1 hover:bg-white dark:hover:bg-ink-800 rounded text-ink-600 dark:text-ink-400"><Minus size={13} /></button>
                                                <span className="text-sm font-semibold w-6 text-center">{item.qty}</span>
                                                <button type="button" onClick={() => updateQty(item.batch_id, 1)} aria-label="Increase" className="p-1 hover:bg-white dark:hover:bg-ink-800 rounded text-ink-600 dark:text-ink-400"><Plus size={13} /></button>
                                            </div>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>

                        <div data-tour="pharmacy-pay" className="p-4 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900">
                            <div className="flex justify-between items-center mb-3">
                                <span className="section-eyebrow">Subtotal</span>
                                <span className="text-xl font-semibold text-ink-900 dark:text-ink-100 tracking-tight">KES {cartTotal.toLocaleString()}</span>
                            </div>
                            <OtcPayBar
                                disabled={cart.length === 0 || isProcessing}
                                onCash={() => handleOTCPay('cash')}
                                onCard={() => {
                                    const ref = window.prompt('Card auth code / reference (optional):') || null;
                                    handleOTCPay('card', { reference: ref });
                                }}
                                onMpesa={(phone) => handleOTCPay('mpesa', { phoneNumber: phone })}
                            />
                        </div>
                    </div>
                </div>
            )}

            {activeTab === 'transactions' && (
                <div data-tour="pharmacy-transactions" className="flex-1 flex flex-col overflow-hidden">
                    <TransactionsTab />
                </div>
            )}

            {payment && (
                <PaymentModal
                    invoiceId={payment.invoiceId}
                    dispenseId={payment.dispenseId}
                    amountDue={payment.amount}
                    patientName={payment.patientName}
                    pendingMpesa={payment.pendingMpesa}
                    onClose={() => setPayment(null)}
                    onSettled={handlePaymentSettled}
                />
            )}

            {activeOrder && actionModal === 'files' && (
                <FilesModal patient={{ patient_id: activeOrder.patient_id, patient_name: activeOrder.patient }}
                    recordId={activeOrder.record_id} onClose={() => setActionModal(null)} />
            )}
            {actionModal === 'queue' && (
                <QueuePatientModal onQueued={fetchRxQueue} onClose={() => setActionModal(null)} />
            )}
        </div>
    );
}


/* ─── Rx dispense, bill panels ──────────────────────────────────────────── */

// Pure helper hoisted to module scope (no component state).
const fmtKES = (v) => `KES ${Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

// Bill Payment Details read-out (MedicentreV3 parity). Total Bill / Amount Due
// come from the resolved dispense lines; the deposit ledger (deposited/used/
// refunded/balance) needs a patient-account endpoint that billing doesn't yet
// expose, so those cells read "-" with a footnote rather than fabricate values.
function BillPaymentDetails({ total }) {
    const cells = [
        { label: 'Amount Deposited', value: '-', muted: true },
        { label: 'Total Amount Used', value: '-', muted: true },
        { label: 'Total Amount Refunded', value: '-', muted: true },
        { label: 'Deposit Balance', value: '-', muted: true },
        { label: 'Total Bill', value: fmtKES(total) },
        { label: 'Amount Due', value: fmtKES(total), strong: true },
    ];
    return (
        <section className="card-flush border border-ink-200 dark:border-ink-800 rounded-xl overflow-hidden">
            <header className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-100 dark:border-ink-800 bg-ink-50/60 dark:bg-ink-800/40">
                <Wallet size={15} className="text-brand-500" />
                <h3 className="text-sm font-semibold text-ink-900 dark:text-ink-100 tracking-tight">Bill Payment Details</h3>
            </header>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-px bg-ink-100 dark:bg-ink-800">
                {cells.map((c) => (
                    <div key={c.label} className="bg-white dark:bg-ink-900 px-4 py-2.5">
                        <span className="block text-2xs font-semibold uppercase tracking-[0.12em] text-ink-400 dark:text-ink-500">{c.label}</span>
                        <span className={`block mt-0.5 text-sm tabular-nums ${c.strong ? 'font-semibold text-ink-900 dark:text-ink-100' : c.muted ? 'text-ink-400 dark:text-ink-500' : 'font-medium text-ink-800 dark:text-ink-200'}`}>{c.value}</span>
                    </div>
                ))}
            </div>
            <p className="px-4 py-1.5 text-2xs text-ink-400 dark:text-ink-500">Amounts finalise on dispense · patient deposit ledger integrates with billing next.</p>
        </section>
    );
}

// Bill Items grid: one row per prescribed line, matched to a stock batch. The
// pharmacist sets the quantity and marks each line packed before dispensing.
function BillItemsTable({ rows, packed, onToggle, onQty }) {
    return (
        <section className="card-flush border border-ink-200 dark:border-ink-800 rounded-xl overflow-hidden">
            <header className="flex items-center justify-between px-4 py-2.5 border-b border-ink-100 dark:border-ink-800 bg-ink-50/60 dark:bg-ink-800/40">
                <h3 className="text-sm font-semibold text-ink-900 dark:text-ink-100 tracking-tight flex items-center gap-2">
                    <Pill size={15} className="text-brand-500" /> Bill Items
                </h3>
                <span className="text-2xs text-ink-500 dark:text-ink-400">{rows.length} line{rows.length === 1 ? '' : 's'}</span>
            </header>
            <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[720px]">
                    <thead>
                        <tr className="text-left text-2xs uppercase tracking-wider">
                            <th className="font-medium">#</th>
                            <th className="font-medium">Item</th>
                            <th className="font-medium">Dosage</th>
                            <th className="font-medium">Freq</th>
                            <th className="font-medium">Duration</th>
                            <th className="font-medium">Stock / Batch</th>
                            <th className="num font-medium">Rate</th>
                            <th className="num font-medium">Qty</th>
                            <th className="num font-medium">Amount</th>
                            <th className="font-medium text-center">Packed</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map(({ line, idx, batch, qty, amount }) => (
                            <tr key={`${idx}-${line.drug}-${line.dosage}`} className={packed[idx] ? 'bg-emerald-50/40 dark:bg-emerald-500/5' : ''}>
                                <td className="text-ink-400">{idx + 1}</td>
                                <td>
                                    <span className="font-medium text-ink-900 dark:text-ink-100">{line.drug}</span>
                                    {line.formulation && <span className="block text-2xs text-ink-400">{line.formulation}</span>}
                                </td>
                                <td className="text-ink-600 dark:text-ink-300">{line.dosage}</td>
                                <td className="text-ink-600 dark:text-ink-300">{line.frequency}</td>
                                <td className="text-ink-600 dark:text-ink-300">{line.duration}</td>
                                <td>
                                    {batch ? (
                                        <span className="text-ink-600 dark:text-ink-300">
                                            <span className="font-mono text-2xs">{batch.batch_number}</span>
                                            <span className={`block text-2xs ${batch.quantity > 0 ? 'text-ink-400' : 'text-rose-600'}`}>avail {batch.quantity}</span>
                                        </span>
                                    ) : (
                                        <span className="inline-flex items-center gap-1 text-2xs text-rose-600"><AlertCircle size={12} /> No stock match</span>
                                    )}
                                </td>
                                <td className="num tabular-nums text-ink-600 dark:text-ink-300">{batch ? fmtKES(batch.unit_price) : '-'}</td>
                                <td className="num">
                                    <input type="number" min="0" max={batch?.quantity ?? undefined}
                                        aria-label={`Quantity for ${line.drug}`}
                                        value={qty || ''} disabled={!batch}
                                        onChange={(e) => onQty(idx, e.target.value)}
                                        className="input py-1 w-20 text-right disabled:opacity-50" />
                                </td>
                                <td className="num tabular-nums font-medium text-ink-800 dark:text-ink-200">{amount ? fmtKES(amount) : '-'}</td>
                                <td className="text-center">
                                    <input type="checkbox" checked={!!packed[idx]} disabled={!batch}
                                        aria-label={`Mark ${line.drug} packed`}
                                        onChange={() => onToggle(idx)}
                                        className="size-4 text-brand-600 rounded border-ink-300 focus:ring-brand-500 disabled:opacity-50" />
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </section>
    );
}


/* ─── OTC pay-straight-away bar ──────────────────────────────────────────── */

function OtcPayBar({ disabled, onCash, onCard, onMpesa }) {
    const [showMpesa, setShowMpesa] = useState(false);
    const [phone, setPhone] = useState('');
    return (
        <div className="space-y-2">
            <div className="grid grid-cols-3 gap-2">
                <button type="button" onClick={onCash} disabled={disabled}
                        className="btn-success py-3 flex flex-col items-center gap-1 text-xs">
                    <Banknote size={18} /><span>Cash</span>
                </button>
                <button type="button" onClick={onCard} disabled={disabled}
                        className="btn-primary py-3 flex flex-col items-center gap-1 text-xs">
                    <CreditCard size={18} /><span>Card</span>
                </button>
                <button type="button" onClick={() => setShowMpesa((s) => !s)} disabled={disabled}
                        className="py-3 rounded-lg bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-700 disabled:opacity-60 flex flex-col items-center gap-1">
                    <Smartphone size={18} /><span>M-Pesa</span>
                </button>
            </div>
            {showMpesa && (
                <div className="flex gap-2 pt-1">
                    <input aria-label="07XXXXXXXX or 2547XXXXXXXX" className="input flex-1" placeholder="07XXXXXXXX or 2547XXXXXXXX"
                           value={phone} onChange={(e) => setPhone(e.target.value)} />
                    <button type="button" onClick={() => onMpesa(phone)} disabled={disabled || !phone}
                            className="px-3 py-2 rounded-lg bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-700 disabled:opacity-60">
                        Send STK
                    </button>
                </div>
            )}
        </div>
    );
}


/* ─── Receipt printer ─────────────────────────────────────────────────────── */

/**
 * Pharmacy receipt. Routed through the shared print engine (rather than
 * writing its own HTML document, as it used to) so it picks up the tenant's
 * letterhead and the same house styles as every other printed document.
 */
function printPharmacyReceipt(receipt) {
    const money = (v) => Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const esc = printUtils.esc;
    const itemsHtml = (receipt.items || []).map(
        (it) => `<tr><td>${esc(it.description)}</td><td class="amount">${money(it.amount)}</td></tr>`
    ).join('') || '<tr><td colspan="2" style="text-align:center;color:#94a3b8;">No items dispensed.</td></tr>';
    const paymentsHtml = (receipt.payments || []).map(
        (p) => `<tr><td>${esc(p.method)}${p.reference ? ` <span style="color:#64748b">${esc(p.reference)}</span>` : ''}</td><td class="amount">${money(p.amount)}</td></tr>`
    ).join('');
    const status = receipt.totals?.status || '';
    const settled = status === 'Paid';

    const body = `
      ${printUtils.header({ docType: settled ? 'Pharmacy Receipt' : 'Pharmacy Invoice', docNumber: receipt.receipt_no })}

      <h1 class="doc-title">${settled ? 'Receipt' : 'Invoice'}</h1>
      <div class="doc-subtitle">
        Status: <span class="badge ${settled ? 'paid' : 'pending'}">${esc(status || 'Pending')}</span>
      </div>

      <div class="panel">
        <h3>Dispense</h3>
        <div class="grid-2">
          <div class="field"><div class="label">Customer</div><div class="value">${esc(receipt.patient || 'Walk-in')}</div></div>
          <div class="field"><div class="label">Receipt no</div><div class="value">${esc(receipt.receipt_no)}</div></div>
          ${receipt.cashier ? `<div class="field"><div class="label">Cashier</div><div class="value">${esc(receipt.cashier)}</div></div>` : ''}
          <div class="field"><div class="label">Dispense #</div><div class="value">${esc(receipt.dispense_id)}</div></div>
        </div>
      </div>

      <table class="line-items">
        <thead><tr><th>Item</th><th class="amount">Amount (KES)</th></tr></thead>
        <tbody>${itemsHtml}</tbody>
      </table>

      <div class="totals">
        <div class="row grand"><span>Total</span><span>KES ${money(receipt.totals?.total)}</span></div>
      </div>

      ${paymentsHtml ? `
        <table class="line-items" style="margin-top:14px">
          <thead><tr><th>Paid via</th><th class="amount">Amount (KES)</th></tr></thead>
          <tbody>${paymentsHtml}</tbody>
        </table>
        <div class="totals">
          <div class="row"><span>Total paid</span><span>${money(receipt.totals?.paid)}</span></div>
          <div class="row"><span>Balance</span><span>${money(receipt.totals?.balance)}</span></div>
        </div>
      ` : ''}

      ${printUtils.footer(settled ? 'Thank you. Settled in full.' : `Status: ${status}`)}
    `;

    printDocument(`${settled ? 'Receipt' : 'Invoice'} ${receipt.receipt_no ?? ''}`, body);
}

/* ─── Transactions tab ────────────────────────────────────────────────────── */

// Pure helper hoisted to module scope (no component state).
const printReceipt = async (dispenseId) => {
    try {
        const r = await apiClient.get(`/pharmacy/dispense/${dispenseId}/receipt`);
        printPharmacyReceipt(r.data);
    } catch (err) {
        toast.error(err?.response?.data?.detail || 'Could not load receipt.');
    }
};

function TransactionsTab() {
    const today = new Date().toISOString().slice(0, 10);
    const firstOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1)
        .toISOString().slice(0, 10);
    const [from, setFrom] = useState(firstOfMonth);
    const [to, setTo] = useState(today);
    const [method, setMethod] = useState('');
    const [status, setStatus] = useState('');
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const params = { from_date: from, to_date: to, limit: 200 };
            if (method) params.method = method;
            if (status) params.status = status;
            const r = await apiClient.get('/pharmacy/transactions', { params });
            setRows(r.data?.items || []);
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not load transactions.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

    const total = rows.reduce((s, r) => s + Number(r.total_cost || 0), 0);
    const paid  = rows.reduce((s, r) => s + Number(r.amount_paid || 0), 0);

    return (
        <div className="card p-4 flex-1 overflow-auto">
            <div className="flex flex-wrap items-end gap-3 mb-4">
                <Field label="From"><input aria-label="From" type="date" className="input" value={from} onChange={e => setFrom(e.target.value)} /></Field>
                <Field label="To"><input aria-label="To" type="date" className="input" value={to} onChange={e => setTo(e.target.value)} /></Field>
                <Field label="Method">
                    <select className="input" value={method} onChange={e => setMethod(e.target.value)}>
                        <option value="">All</option>
                        <option>Cash</option>
                        <option>M-Pesa</option>
                        <option>Card</option>
                        <option value="Unpaid">Unpaid</option>
                    </select>
                </Field>
                <Field label="Status">
                    <select className="input" value={status} onChange={e => setStatus(e.target.value)}>
                        <option value="">All</option>
                        <option>Paid</option>
                        <option>Partially Paid</option>
                        <option>Pending</option>
                        <option>Pending M-Pesa</option>
                    </select>
                </Field>
                <button type="button" onClick={load}
                        className="btn-primary text-sm"
                        disabled={loading}>
                    {loading ? 'Loading...' : 'Apply'}
                </button>
                <div className="ml-auto text-xs text-ink-600 dark:text-ink-400">
                    <span className="mr-3">Charged: <strong>KES {total.toLocaleString()}</strong></span>
                    <span>Collected: <strong>KES {paid.toLocaleString()}</strong></span>
                </div>
            </div>

            <div className="overflow-x-auto border border-ink-200/70 rounded-lg">
                <table className="table-clean table-sticky">
                    <thead>
                        <tr>
                            <th className="font-medium">Date</th>
                            <th className="font-medium">Item</th>
                            <th className="num font-medium">Qty</th>
                            <th className="num font-medium">Total</th>
                            <th className="font-medium">Customer</th>
                            <th className="font-medium">Method</th>
                            <th className="font-medium">Status</th>
                            <th className="font-medium">Cashier</th>
                            <th aria-label="Actions"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr><td colSpan={9} className="px-3 py-6 text-ink-500">Loading...</td></tr>
                        ) : rows.length === 0 ? (
                            <tr><td colSpan={9} className="px-3 py-6 text-ink-500">No transactions in this window.</td></tr>
                        ) : rows.map((r) => (
                            <tr key={r.dispense_id}>
                                <td className="whitespace-nowrap">
                                    {r.dispensed_at ? new Date(r.dispensed_at).toLocaleString() : '-'}
                                </td>
                                <td>{r.item_name}</td>
                                <td className="num">{r.quantity}</td>
                                <td className="num font-mono">{Number(r.total_cost).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                                <td>{r.patient_id ? `#${r.patient_id}` : 'Walk-in'}</td>
                                <td>{r.payment_method || '-'}</td>
                                <td>
                                    <span
                                        aria-label={`Invoice status: ${r.invoice_status}`}
                                        className={'text-xs px-2 py-0.5 rounded-md ' + (
                                        r.invoice_status === 'Paid' ? 'bg-emerald-50 text-emerald-700' :
                                        r.invoice_status === 'Partially Paid' ? 'bg-amber-50 text-amber-700' :
                                        r.invoice_status?.includes('Pending') ? 'bg-sky-50 text-sky-700' :
                                        'bg-ink-50 dark:bg-ink-900/40 text-ink-600 dark:text-ink-400'
                                    )}>{r.invoice_status}</span>
                                </td>
                                <td className="text-ink-600 dark:text-ink-400">{r.cashier || '-'}</td>
                                <td className="num">
                                    <button type="button" onClick={() => printReceipt(r.dispense_id)}
                                            className="inline-flex items-center gap-1 text-xs text-brand-700 hover:underline">
                                        <ReceiptText size={12} /> Receipt
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

function Field({ label, children }) {
    return (
        <label className="block">
            <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">{label}</span>
            {children}
        </label>
    );
}


/* ─── Payment modal ───────────────────────────────────────────────────────── */

const POLL_MS = 3000;
const STK_TIMEOUT = 60;   // seconds the customer has to enter their PIN

function PaymentModal({ invoiceId, dispenseId, amountDue, patientName, pendingMpesa, onClose, onSettled }) {
    const [method, setMethod] = useState('cash');     // 'cash' | 'mpesa'
    const [amount, setAmount] = useState(amountDue ? Number(amountDue).toFixed(2) : '');
    const [phone, setPhone] = useState('');
    const [reference, setReference] = useState('');
    const [submitting, setSubmitting] = useState(false);
    // M-Pesa wait state: null = form, else 'waiting' | 'success' | 'failed'.
    const [mpesaStatus, setMpesaStatus] = useState(pendingMpesa?.transaction_id ? 'waiting' : null);
    const [secondsLeft, setSecondsLeft] = useState(STK_TIMEOUT);
    const [mpesaError, setMpesaError] = useState(null);
    const [mpesaReceipt, setMpesaReceipt] = useState(null);
    // One idempotency key per STK-push attempt: reused if this same attempt
    // needs resubmitting, cleared by retry() so "Try again" after a
    // resolved failure sends a genuinely new prompt rather than replaying
    // the dead one.
    const idemRef = useRef(null);

    // Poll our own DB row (settled by the verified Daraja callback) while a
    // push is pending, and run a visible countdown alongside it.
    // Cleanup exists: the cleanup clears both intervals.
    // react-doctor-disable-next-line react-doctor/effect-needs-cleanup
    useEffect(() => {
        if (mpesaStatus !== 'waiting') return undefined;

        const tick = setInterval(() => {
            setSecondsLeft((s) => {
                if (s <= 1) {
                    setMpesaStatus('failed');
                    setMpesaError('No PIN was entered before the prompt expired.');
                    return 0;
                }
                return s - 1;
            });
        }, 1000);

        const poll = setInterval(async () => {
            try {
                const r = await apiClient.get(`/pharmacy/dispense/${dispenseId}/payment-status`);
                if (r.data?.invoice_status === 'Paid' || r.data?.mpesa_status === 'Success') {
                    setMpesaReceipt(r.data?.mpesa_receipt_number);
                    setMpesaStatus('success');
                    toast.success(`M-Pesa receipt ${r.data?.mpesa_receipt_number || ''} confirmed.`);
                    setTimeout(onSettled, 1800);
                } else if (r.data?.mpesa_status === 'Failed') {
                    setMpesaStatus('failed');
                    setMpesaError(r.data?.mpesa_result_desc || 'Cancelled by the customer.');
                }
            } catch {
                // Transient: keep polling until the countdown ends.
            }
        }, POLL_MS);

        return () => { clearInterval(tick); clearInterval(poll); };
    }, [mpesaStatus, dispenseId, onSettled]);

    // Live push: flips the modal the instant the webhook settles, ahead of
    // the next poll. Polling above stays as the fallback.
    usePaymentSocket(mpesaStatus === 'waiting', (data) => {
        if (mpesaStatus !== 'waiting' || data.dispense_id !== dispenseId) return;
        if (data.status === 'Success') {
            setMpesaReceipt(data.receipt_number);
            setMpesaStatus('success');
            toast.success(`M-Pesa receipt ${data.receipt_number || ''} confirmed.`);
            setTimeout(onSettled, 1800);
        } else if (data.status === 'Failed') {
            setMpesaStatus('failed');
            setMpesaError(data.result_desc || 'Cancelled by the customer.');
        }
    });

    const retry = () => {
        setMpesaStatus(null);
        setMpesaError(null);
        setMpesaReceipt(null);
        setSecondsLeft(STK_TIMEOUT);
        idemRef.current = null; // the next send is a new attempt, not a retry
    };

    const submit = async () => {
        const amt = Number(amount);
        if (!amt || amt <= 0) return toast.error('Enter a valid amount.');
        if (method === 'mpesa' && !phone) return toast.error('M-Pesa needs a phone number.');
        if (method === 'mpesa' && !idemRef.current) idemRef.current = newIdempotencyKey();

        setSubmitting(true);
        try {
            const payload = {
                method,
                amount: amt,
                phone_number: method === 'mpesa' ? phone : null,
                transaction_reference: reference || null,
                idempotency_key: method === 'mpesa' ? idemRef.current : null,
            };
            const res = await apiClient.post(`/pharmacy/dispense/${dispenseId}/pay`, payload);

            if (method === 'cash') {
                toast.success(`Cash payment recorded. Invoice ${res.data?.invoice_status}.`);
                onSettled();
            } else if (method === 'mpesa') {
                toast.success('STK push sent. Customer to confirm on their phone.');
                // Start a fresh countdown alongside the wait state here, rather
                // than resetting it inside the polling effect when the status
                // changes. (Initial mount and retry() also seed STK_TIMEOUT.)
                setSecondsLeft(STK_TIMEOUT);
                setMpesaStatus('waiting');
            }
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Payment failed.');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-ink-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-ink-900 rounded-xl shadow-overlay w-full max-w-md">
                <div className="flex items-center justify-between p-4 border-b border-ink-100 dark:border-ink-800">
                    <div>
                        <h3 className="text-sm font-semibold text-ink-900 dark:text-ink-100">Collect payment</h3>
                        <p className="text-xs text-ink-500">
                            {patientName ? `${patientName} · ` : ''}Invoice #{invoiceId} · KES {Number(amountDue || 0).toLocaleString()}
                        </p>
                    </div>
                    <button type="button" onClick={onClose} className="text-ink-400 hover:text-ink-700" aria-label="Close">
                        <XIcon size={18} />
                    </button>
                </div>

                <div className="p-5 space-y-4">
                    {mpesaStatus ? (
                        <MpesaStkProgress
                            status={mpesaStatus}
                            phone={phone || pendingMpesa?.phone}
                            secondsLeft={secondsLeft}
                            total={STK_TIMEOUT}
                            receipt={mpesaReceipt}
                            errorDesc={mpesaError}
                            onRetry={retry}
                        />
                    ) : (
                        <>
                            <div className="flex gap-2 border-b border-ink-100 dark:border-ink-800">
                                <button type="button" onClick={() => setMethod('cash')}
                                        className={'flex items-center gap-2 px-3 py-2 text-sm font-medium border-b-2 -mb-px ' +
                                            (method === 'cash' ? 'border-brand-600 text-brand-700' : 'border-transparent text-ink-500')}>
                                    <Banknote size={14} /> Cash
                                </button>
                                <button type="button" onClick={() => setMethod('mpesa')}
                                        className={'flex items-center gap-2 px-3 py-2 text-sm font-medium border-b-2 -mb-px ' +
                                            (method === 'mpesa' ? 'border-brand-600 text-brand-700' : 'border-transparent text-ink-500')}>
                                    <Smartphone size={14} /> M-Pesa
                                </button>
                                <button type="button" disabled
                                        className="flex items-center gap-2 px-3 py-2 text-sm font-medium border-b-2 -mb-px border-transparent text-ink-300 cursor-not-allowed"
                                        title="Card integration coming soon">
                                    <CreditCard size={14} /> Card
                                </button>
                            </div>

                            <label className="block">
                                <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">Amount</span>
                                <input type="number" step="0.01" className="input" value={amount}
                                       onChange={(e) => setAmount(e.target.value)} />
                            </label>

                            {method === 'mpesa' && (
                                <label className="block">
                                    <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">Phone number</span>
                                    <input className="input" value={phone}
                                           onChange={(e) => setPhone(e.target.value)}
                                           placeholder="07XXXXXXXX or 2547XXXXXXXX" />
                                </label>
                            )}

                            <label className="block">
                                <span className="block text-xs font-medium text-ink-600 dark:text-ink-400 mb-1">
                                    Reference (optional)
                                </span>
                                <input className="input" value={reference}
                                       onChange={(e) => setReference(e.target.value)}
                                       placeholder="Receipt no., notes, etc." />
                            </label>

                            <div className="flex justify-end gap-2 pt-2">
                                <button type="button" onClick={onClose}
                                        className="px-3 py-2 rounded-lg border border-ink-200 dark:border-ink-800 text-sm font-medium hover:bg-ink-50 dark:hover:bg-ink-800/50">
                                    Cancel
                                </button>
                                <button type="button" onClick={submit} disabled={submitting}
                                        className="px-3 py-2 rounded-lg bg-brand-600 text-white text-sm font-medium hover:bg-brand-700 disabled:opacity-60">
                                    {submitting ? 'Sending…' : (method === 'mpesa' ? 'Send STK push' : 'Record cash')}
                                </button>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}