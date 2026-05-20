import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
    Search, Pill, CheckCircle2, AlertCircle, Clock,
    ChevronDown, ChevronUp, Package, Printer, XCircle,
    FileWarning, ShoppingCart, Plus, Minus, Trash2, CreditCard, Store, Activity,
    Banknote, Smartphone, X as XIcon, ReceiptText, History,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { printPrescription } from '../utils/printTemplates';
import PageHeader from '../components/PageHeader';

export default function Pharmacy() {
    // --- APP STATE ---
    const [activeTab, setActiveTab] = useState('rx'); // 'rx' | 'otc' | 'transactions'
    const [isLoading, setIsLoading] = useState(false);
    const [isProcessing, setIsProcessing] = useState(false);

    // --- RX FULFILLMENT STATE (DYNAMIC) ---
    const [queue, setQueue] = useState([]);
    const [isLoadingQueue, setIsLoadingQueue] = useState(true);
    const [activeOrder, setActiveOrder] = useState(null);
    const [isQueueOpen, setIsQueueOpen] = useState(true);

    // --- OTC POINT OF SALE STATE (RETAIL) ---
    const [otcSearch, setOtcSearch] = useState('');
    const [inventory, setInventory] = useState([]);
    const [cart, setCart] = useState([]);

    // --- PAYMENT MODAL STATE (post-dispense) ---
    // payment.invoice_id is the rolled-up invoice for the dispense run;
    // payment.lastDispenseId is the dispense whose /pay endpoint we'll hit
    // (any of the items work — they share the invoice).
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
    const genKey = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

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
                notes: it.notes || null,
            });
            responses.push(res.data);
        }
        return responses;
    };

    // Pay-straight-away OTC checkout: dispense the cart, then immediately
    // process the chosen method against the rolled-up invoice. No "choose
    // method" modal — the cashier already picked Cash/Card/M-Pesa.
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
            });

            if (method === 'mpesa') {
                toast.success('STK push sent. Customer to confirm on their phone.');
                // Open the modal in polling mode so the cashier can watch.
                setPayment({
                    invoiceId: last.invoice_id,
                    dispenseId: last.dispense_id,
                    amount,
                    patientName: 'Walk-in',
                    pendingMpesa: { checkout_request_id: res.data?.checkout_request_id,
                                    mpesa_transaction_id: res.data?.mpesa_transaction_id },
                });
            } else {
                toast.success(`${method === 'card' ? 'Card' : 'Cash'} payment recorded.`);
                // Receipt prints directly without the modal round-trip.
                try {
                    const r = await apiClient.get(`/pharmacy/dispense/${last.dispense_id}/receipt`);
                    printPharmacyReceipt(r.data);
                } catch { /* silently skip — payment still landed */ }
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
            setActiveOrder(null);
            setIsQueueOpen(true);
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Return failed.');
        }
    };

    const handleRxDispense = async () => {
        if (!activeOrder) return;
        if (cart.length === 0) {
            return toast.error("Add the prescribed items to the cart first.");
        }
        setIsProcessing(true);
        try {
            const responses = await dispenseItems(cart, {
                patient_id: activeOrder.patient_id,
                record_id: activeOrder.record_id,
            });
            toast.success(`Prescription ${activeOrder.id} dispensed.`);
            fetchPharmacyInventory();

            // Open payment modal seeded from the rolled-up invoice.
            const last = responses[responses.length - 1];
            if (last?.invoice_id) {
                setPayment({
                    invoiceId: last.invoice_id,
                    dispenseId: last.dispense_id,
                    amount: last.invoice_balance ?? cartTotal,
                    patientName: activeOrder.patient_name,
                });
            } else {
                // No invoice (walk-in) — just clear and exit.
                setCart([]);
                setQueue(queue.filter(q => q.id !== activeOrder.id));
                setActiveOrder(null);
                setIsQueueOpen(true);
            }
        } catch (error) {
            toast.error(error?.response?.data?.detail || "Failed to dispense prescription.");
        } finally {
            setIsProcessing(false);
        }
    };

    const handlePaymentSettled = async (settledPayment) => {
        // Called by the modal when payment completes successfully.
        // Fire the receipt print before we tear down state — the modal's
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
            setActiveOrder(null);
            setIsQueueOpen(true);
        }
    };

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">
            <PageHeader
                eyebrow="Dispensary"
                icon={Pill}
                title="Pharmacy"
                subtitle="Fulfil prescriptions, dispense over-the-counter sales, and track stock movements."
            />
            {/* GLOBAL PHARMACY HEADER & TABS */}
            <div className="card p-2 flex flex-col sm:flex-row items-stretch sm:items-center justify-between shrink-0 gap-2">
                <div role="tablist" aria-label="Pharmacy mode" className="flex bg-ink-100/70 p-1 rounded-xl w-full max-w-md">
                    <button role="tab" aria-selected={activeTab === 'rx'} onClick={() => setActiveTab('rx')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium transition-all ${activeTab === 'rx' ? 'bg-white text-ink-900 shadow-soft ring-1 ring-ink-200/70' : 'text-ink-600 hover:text-ink-900'}`}>
                        <Pill size={16} className={activeTab === 'rx' ? 'text-brand-600' : 'text-ink-400'} /> Rx Fulfillment
                    </button>
                    <button role="tab" aria-selected={activeTab === 'otc'} onClick={() => setActiveTab('otc')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium transition-all ${activeTab === 'otc' ? 'bg-white text-ink-900 shadow-soft ring-1 ring-ink-200/70' : 'text-ink-600 hover:text-ink-900'}`}>
                        <Store size={16} className={activeTab === 'otc' ? 'text-accent-600' : 'text-ink-400'} /> OTC Point of Sale
                    </button>
                    <button role="tab" aria-selected={activeTab === 'transactions'} onClick={() => setActiveTab('transactions')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium transition-all ${activeTab === 'transactions' ? 'bg-white text-ink-900 shadow-soft ring-1 ring-ink-200/70' : 'text-ink-600 hover:text-ink-900'}`}>
                        <History size={16} className={activeTab === 'transactions' ? 'text-brand-600' : 'text-ink-400'} /> Transactions
                    </button>
                </div>
                <div className="text-right px-3 text-xs font-semibold text-ink-500">
                    {new Date().toLocaleDateString('en-KE', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                </div>
            </div>

            {/* ========================================= */}
            {/* MODE 1: PRESCRIPTION FULFILLMENT (CLINICAL) */}
            {/* ========================================= */}
            {activeTab === 'rx' && (
                <>
                    <div className="card shrink-0 flex flex-col z-20">
                        <button onClick={() => setIsQueueOpen(!isQueueOpen)} className="w-full p-4 flex justify-between items-center bg-ink-50/60 hover:bg-brand-50/40 transition-colors rounded-t-2xl focus:outline-none">
                            <div className="flex items-center gap-3">
                                <Package className="text-brand-600" size={18} />
                                <h2 className="font-semibold text-ink-900 text-base tracking-tight">Pending prescriptions</h2>
                                <span className="badge-warn">{queue.length} Awaiting</span>
                            </div>
                            <span className="text-ink-500">{isQueueOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</span>
                        </button>

                        {isQueueOpen && (
                            <div className="border-t border-ink-100 p-4 bg-white rounded-b-2xl">
                                {isLoadingQueue ? (
                                    <div className="text-center py-8 text-ink-400">
                                        <Activity className="animate-spin mx-auto mb-2 text-brand-500" size={20} />
                                        Syncing prescription queue&hellip;
                                    </div>
                                ) : queue.length === 0 ? (
                                    <div className="text-center py-8 text-ink-400">No pending prescriptions at this time.</div>
                                ) : (
                                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                        {queue.map((order) => {
                                            const active = activeOrder?.id === order.id;
                                            return (
                                                <button key={order.id} type="button" onClick={() => {setActiveOrder(order); setIsQueueOpen(false);}} className={`text-left p-3 rounded-xl border transition-all duration-150 ${active ? 'bg-brand-50/60 border-brand-400 ring-2 ring-brand-500/15' : 'bg-white border-ink-200 hover:border-brand-300 hover:-translate-y-0.5'}`}>
                                                    <div className="flex justify-between items-start mb-2">
                                                        <h3 className="font-semibold text-sm text-ink-900">{order.patient}</h3>
                                                        {order.priority === 'High' && <AlertCircle size={14} className="text-rose-500 animate-pulse-soft" />}
                                                    </div>
                                                    <div className="flex justify-between items-center text-xs text-brand-700 font-mono mb-1"><span>{order.id}</span></div>
                                                    <div className="flex justify-between items-center text-xs text-ink-400"><span>{order.doctor}</span><span className="bg-ink-100 px-2 py-0.5 rounded-full text-ink-600 flex items-center gap-1"><Clock size={10} /> {order.time}</span></div>
                                                </button>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    <div className="flex-1 card overflow-hidden flex flex-col z-10 relative">
                        {!activeOrder ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-ink-400 bg-ink-50/40">
                                <Pill size={56} className="mb-4 text-ink-300" strokeWidth={1.5} />
                                <h3 className="text-base font-semibold text-ink-600 mb-1">Select a prescription</h3>
                                <p className="text-sm">Choose an order from the queue to dispense.</p>
                            </div>
                        ) : (
                            <>
                                <div className="shrink-0 flex flex-col">
                                    <div className="p-4 border-b border-ink-100 bg-white flex justify-between items-center z-10">
                                        <div className="flex items-center gap-3">
                                            <div className="w-11 h-11 rounded-full bg-gradient-to-br from-brand-400 to-accent-500 text-white flex items-center justify-center shadow-glow"><FileWarning size={18} /></div>
                                            <div>
                                                <h1 className="text-lg font-semibold text-ink-900 tracking-tight">Rx: {activeOrder.id}</h1>
                                                <p className="text-xs font-medium text-ink-500">{activeOrder.patient} &middot; {activeOrder.op_no} &middot; {activeOrder.doctor}</p>
                                            </div>
                                        </div>
                                        {activeOrder.allergies && (
                                            <div className="bg-rose-50 ring-1 ring-rose-100 px-3 py-2 rounded-xl flex items-center gap-2 animate-pulse-soft">
                                                <AlertCircle size={18} className="text-rose-600" />
                                                <div>
                                                    <p className="text-2xs font-semibold text-rose-700 uppercase tracking-[0.14em]">Allergies</p>
                                                    <p className="text-xs font-semibold text-rose-700">{activeOrder.allergies}</p>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-3 bg-ink-50/40 custom-scrollbar">
                                    {activeOrder.prescriptions?.map((med, idx) => (
                                        <div key={idx} className="card-flush p-5">
                                            <div className="flex justify-between items-start gap-4">
                                                <div className="flex-1">
                                                    <h4 className="font-semibold text-base text-ink-900 tracking-tight">{med.drug}</h4>
                                                    <div className="flex gap-5 mt-3 text-sm text-ink-700">
                                                        <div><span className="block text-2xs font-semibold text-ink-400 uppercase tracking-wider">Dosage</span>{med.dosage}</div>
                                                        <div><span className="block text-2xs font-semibold text-ink-400 uppercase tracking-wider">Freq</span>{med.frequency}</div>
                                                        <div><span className="block text-2xs font-semibold text-ink-400 uppercase tracking-wider">Duration</span>{med.duration}</div>
                                                    </div>
                                                </div>
                                                <label className="flex items-center gap-2 text-xs font-medium text-ink-700 cursor-pointer p-2.5 border border-ink-200 rounded-lg hover:bg-ink-50 shrink-0">
                                                    <input type="checkbox" className="w-4 h-4 text-brand-600 rounded border-ink-300 focus:ring-brand-500" /> Packed
                                                </label>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div className="p-4 border-t border-ink-100 bg-white flex flex-wrap justify-end gap-2 shrink-0 z-10">
                                    <button
                                        onClick={() => printPrescription({
                                            patient: { full_name: activeOrder.patient, outpatient_no: activeOrder.op_no, allergies: activeOrder.allergies },
                                            doctor:  { full_name: activeOrder.doctor, license_number: activeOrder.doctor_license },
                                            items:   (activeOrder.prescriptions || []).map(p => ({ drug_name: p.drug, dosage: p.dosage, frequency: p.frequency, duration: p.duration, route: p.route || p.notes })),
                                            notes:   activeOrder.clinical_notes,
                                            recordId: activeOrder.id,
                                        })}
                                        className="btn-secondary"
                                    >
                                        <Printer size={15} /> Print Rx
                                    </button>
                                    <button onClick={handleReturnToDoctor} className="btn-secondary text-rose-600 border-rose-200 hover:bg-rose-50"><XCircle size={15} /> Return to doctor</button>
                                    <button onClick={handleRxDispense} disabled={isProcessing} className="btn-primary">
                                        <CheckCircle2 size={16} /> {isProcessing ? 'Processing…' : 'Dispense & close'}
                                    </button>
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
                    <div className="flex-1 card flex flex-col overflow-hidden">
                        <div className="p-4 border-b border-ink-100 bg-ink-50/40">
                            <div className="relative">
                                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                                <input
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
                                        <div key={item.batch_id} className="border border-ink-200 rounded-xl p-3 hover:border-accent-300 hover:shadow-soft transition-all bg-white flex flex-col justify-between">
                                            <div>
                                                <div className="flex justify-between items-start mb-1 gap-2">
                                                    <h4 className="font-semibold text-sm text-ink-900">{item.name}</h4>
                                                    <span className="badge-neutral">{item.category}</span>
                                                </div>
                                                <div className="flex items-center gap-2 mt-2">
                                                    <span className="font-semibold text-accent-700">KES {item.unit_price}</span>
                                                    <span className="text-ink-300">·</span>
                                                    <span className={`text-xs font-medium ${item.quantity > 0 ? 'text-ink-500' : 'text-rose-600'}`}>Stock: {item.quantity}</span>
                                                </div>
                                                <div className="text-2xs text-ink-400 mt-1 uppercase tracking-wider font-mono">Batch: {item.batch_number}</div>
                                            </div>
                                            <button
                                                onClick={() => addToCart(item)}
                                                disabled={item.quantity === 0}
                                                className="mt-3 w-full py-1.5 bg-ink-50 border border-ink-200 hover:bg-accent-50 hover:border-accent-300 hover:text-accent-700 text-ink-700 text-sm font-semibold rounded-lg flex items-center justify-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
                        <div className="p-4 border-b border-ink-100 bg-ink-50/40 flex justify-between items-center">
                            <h3 className="font-semibold text-ink-900 flex items-center gap-2 tracking-tight">
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
                                            <h4 className="font-semibold text-sm text-ink-800 line-clamp-1">{item.name}</h4>
                                            <button onClick={() => removeFromCart(item.batch_id)} aria-label="Remove" className="text-ink-400 hover:text-rose-600 transition-colors p-0.5"><Trash2 size={15} /></button>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-xs font-medium text-ink-500">KES {item.unit_price} &times; {item.qty}</span>
                                            <div className="flex items-center gap-1 bg-ink-50 border border-ink-200 rounded-lg p-0.5">
                                                <button onClick={() => updateQty(item.batch_id, -1)} aria-label="Decrease" className="p-1 hover:bg-white rounded text-ink-600"><Minus size={13} /></button>
                                                <span className="text-sm font-semibold w-6 text-center">{item.qty}</span>
                                                <button onClick={() => updateQty(item.batch_id, 1)} aria-label="Increase" className="p-1 hover:bg-white rounded text-ink-600"><Plus size={13} /></button>
                                            </div>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>

                        <div className="p-4 border-t border-ink-100 bg-white">
                            <div className="flex justify-between items-center mb-3">
                                <span className="section-eyebrow">Subtotal</span>
                                <span className="text-xl font-semibold text-ink-900 tracking-tight">KES {cartTotal.toLocaleString()}</span>
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
                <TransactionsTab />
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
        </div>
    );
}


/* ─── OTC pay-straight-away bar ──────────────────────────────────────────── */

function OtcPayBar({ disabled, onCash, onCard, onMpesa }) {
    const [showMpesa, setShowMpesa] = useState(false);
    const [phone, setPhone] = useState('');
    return (
        <div className="space-y-2">
            <div className="grid grid-cols-3 gap-2">
                <button onClick={onCash} disabled={disabled}
                        className="btn-success py-3 flex flex-col items-center gap-1 text-xs">
                    <Banknote size={18} /><span>Cash</span>
                </button>
                <button onClick={onCard} disabled={disabled}
                        className="btn-primary py-3 flex flex-col items-center gap-1 text-xs">
                    <CreditCard size={18} /><span>Card</span>
                </button>
                <button onClick={() => setShowMpesa((s) => !s)} disabled={disabled}
                        className="py-3 rounded-lg bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-700 disabled:opacity-60 flex flex-col items-center gap-1">
                    <Smartphone size={18} /><span>M-Pesa</span>
                </button>
            </div>
            {showMpesa && (
                <div className="flex gap-2 pt-1">
                    <input className="input flex-1" placeholder="07XXXXXXXX or 2547XXXXXXXX"
                           value={phone} onChange={(e) => setPhone(e.target.value)} />
                    <button onClick={() => onMpesa(phone)} disabled={disabled || !phone}
                            className="px-3 py-2 rounded-lg bg-emerald-600 text-white text-xs font-medium hover:bg-emerald-700 disabled:opacity-60">
                        Send STK
                    </button>
                </div>
            )}
        </div>
    );
}


/* ─── Receipt printer ─────────────────────────────────────────────────────── */

function printPharmacyReceipt(receipt) {
    const win = window.open('', '_blank', 'width=420,height=720');
    if (!win) {
        toast.error('Pop-up blocked — allow pop-ups to print the receipt.');
        return;
    }
    const money = (v) => Number(v ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const itemsHtml = (receipt.items || []).map(
        (it) => `<tr><td>${escapeHtml(it.description)}</td><td class="r">${money(it.amount)}</td></tr>`
    ).join('');
    const paymentsHtml = (receipt.payments || []).map(
        (p) => `<tr><td>${escapeHtml(p.method)}${p.reference ? ` <span class="muted">${escapeHtml(p.reference)}</span>` : ''}</td><td class="r">${money(p.amount)}</td></tr>`
    ).join('');
    const issued = receipt.issued_at ? new Date(receipt.issued_at).toLocaleString() : '';
    const html = `<!doctype html><html><head><meta charset="utf-8"/>
<title>${escapeHtml(receipt.receipt_no)}</title>
<style>
  body { font-family: ui-sans-serif, system-ui, sans-serif; padding: 16px; color: #1f2937; }
  .hd { text-align: center; margin-bottom: 12px; }
  .hd h1 { margin: 0; font-size: 18px; }
  .hd p { margin: 2px 0; font-size: 11px; color: #6b7280; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { padding: 4px 0; }
  th { text-align: left; border-bottom: 1px dashed #9ca3af; }
  .r { text-align: right; font-variant-numeric: tabular-nums; }
  .muted { color: #6b7280; font-size: 10px; }
  .total { border-top: 1px solid #111; font-weight: 600; }
  .meta { font-size: 11px; color: #6b7280; margin: 8px 0; }
  .foot { text-align: center; margin-top: 16px; font-size: 11px; color: #6b7280; }
  @media print { @page { margin: 4mm; } }
</style></head><body>
  <div class="hd">
    <h1>${escapeHtml(receipt.hospital?.name || 'MediFleet')}</h1>
    ${receipt.hospital?.tagline ? `<p>${escapeHtml(receipt.hospital.tagline)}</p>` : ''}
    <p>Receipt: <strong>${escapeHtml(receipt.receipt_no)}</strong></p>
    <p>${escapeHtml(issued)}</p>
  </div>
  <div class="meta">
    Customer: ${escapeHtml(receipt.patient || 'Walk-in')}<br/>
    ${receipt.cashier ? `Cashier: ${escapeHtml(receipt.cashier)}<br/>` : ''}
    Dispense #: ${receipt.dispense_id}
  </div>
  <table>
    <thead><tr><th>Item</th><th class="r">Amount</th></tr></thead>
    <tbody>${itemsHtml}</tbody>
    <tfoot>
      <tr class="total"><td>Total</td><td class="r">KES ${money(receipt.totals?.total)}</td></tr>
    </tfoot>
  </table>
  ${paymentsHtml ? `
    <table style="margin-top:10px">
      <thead><tr><th>Paid via</th><th class="r">Amount</th></tr></thead>
      <tbody>${paymentsHtml}</tbody>
      <tfoot>
        <tr class="total"><td>Total paid</td><td class="r">KES ${money(receipt.totals?.paid)}</td></tr>
        <tr><td>Balance</td><td class="r">KES ${money(receipt.totals?.balance)}</td></tr>
      </tfoot>
    </table>
  ` : ''}
  <div class="foot">Thank you. ${receipt.totals?.status === 'Paid' ? 'Settled in full.' : `Status: ${escapeHtml(receipt.totals?.status || '')}`}</div>
  <script>window.onload = function(){ window.print(); }</script>
</body></html>`;
    win.document.open();
    win.document.write(html);
    win.document.close();
}

function escapeHtml(s) {
    if (s == null) return '';
    return String(s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}


/* ─── Transactions tab ────────────────────────────────────────────────────── */

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

    const printReceipt = async (dispenseId) => {
        try {
            const r = await apiClient.get(`/pharmacy/dispense/${dispenseId}/receipt`);
            printPharmacyReceipt(r.data);
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Could not load receipt.');
        }
    };

    const total = rows.reduce((s, r) => s + Number(r.total_cost || 0), 0);
    const paid  = rows.reduce((s, r) => s + Number(r.amount_paid || 0), 0);

    return (
        <div className="card p-4 flex-1 overflow-auto">
            <div className="flex flex-wrap items-end gap-3 mb-4">
                <Field label="From"><input type="date" className="input" value={from} onChange={e => setFrom(e.target.value)} /></Field>
                <Field label="To"><input type="date" className="input" value={to} onChange={e => setTo(e.target.value)} /></Field>
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
                <button onClick={load}
                        className="btn-primary text-sm"
                        disabled={loading}>
                    {loading ? 'Loading...' : 'Apply'}
                </button>
                <div className="ml-auto text-xs text-ink-600">
                    <span className="mr-3">Charged: <strong>KES {total.toLocaleString()}</strong></span>
                    <span>Collected: <strong>KES {paid.toLocaleString()}</strong></span>
                </div>
            </div>

            <div className="overflow-x-auto border border-ink-200/70 rounded-lg">
                <table className="w-full text-sm">
                    <thead className="bg-ink-50/60 text-ink-600">
                        <tr>
                            <th className="text-left px-3 py-2 font-medium">Date</th>
                            <th className="text-left px-3 py-2 font-medium">Item</th>
                            <th className="text-right px-3 py-2 font-medium">Qty</th>
                            <th className="text-right px-3 py-2 font-medium">Total</th>
                            <th className="text-left px-3 py-2 font-medium">Customer</th>
                            <th className="text-left px-3 py-2 font-medium">Method</th>
                            <th className="text-left px-3 py-2 font-medium">Status</th>
                            <th className="text-left px-3 py-2 font-medium">Cashier</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                        {loading ? (
                            <tr><td colSpan={9} className="px-3 py-6 text-ink-500">Loading...</td></tr>
                        ) : rows.length === 0 ? (
                            <tr><td colSpan={9} className="px-3 py-6 text-ink-500">No transactions in this window.</td></tr>
                        ) : rows.map((r) => (
                            <tr key={r.dispense_id}>
                                <td className="px-3 py-1.5 whitespace-nowrap">
                                    {r.dispensed_at ? new Date(r.dispensed_at).toLocaleString() : '—'}
                                </td>
                                <td className="px-3 py-1.5">{r.item_name}</td>
                                <td className="px-3 py-1.5 text-right">{r.quantity}</td>
                                <td className="px-3 py-1.5 text-right font-mono">{Number(r.total_cost).toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                                <td className="px-3 py-1.5">{r.patient_id ? `#${r.patient_id}` : 'Walk-in'}</td>
                                <td className="px-3 py-1.5">{r.payment_method || '—'}</td>
                                <td className="px-3 py-1.5">
                                    <span className={'text-xs px-2 py-0.5 rounded-md ' + (
                                        r.invoice_status === 'Paid' ? 'bg-emerald-50 text-emerald-700' :
                                        r.invoice_status === 'Partially Paid' ? 'bg-amber-50 text-amber-700' :
                                        r.invoice_status?.includes('Pending') ? 'bg-sky-50 text-sky-700' :
                                        'bg-ink-50 text-ink-600'
                                    )}>{r.invoice_status}</span>
                                </td>
                                <td className="px-3 py-1.5 text-ink-600">{r.cashier || '—'}</td>
                                <td className="px-3 py-1.5 text-right">
                                    <button onClick={() => printReceipt(r.dispense_id)}
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
            <span className="block text-xs font-medium text-ink-600 mb-1">{label}</span>
            {children}
        </label>
    );
}


/* ─── Payment modal ───────────────────────────────────────────────────────── */

const POLL_MS = 3000;
const POLL_TIMEOUT_MS = 90_000;

function PaymentModal({ invoiceId, dispenseId, amountDue, patientName, pendingMpesa, onClose, onSettled }) {
    const [method, setMethod] = useState('cash');     // 'cash' | 'mpesa'
    const [amount, setAmount] = useState(amountDue ? Number(amountDue).toFixed(2) : '');
    const [phone, setPhone] = useState('');
    const [reference, setReference] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const [pollingTxnId, setPollingTxnId] = useState(pendingMpesa?.mpesa_transaction_id ?? null);
    const [pollStatus, setPollStatus] = useState(null);

    // Poll the dispense's payment status while M-Pesa is pending.
    useEffect(() => {
        if (!pollingTxnId) return undefined;
        const startedAt = Date.now();
        const interval = setInterval(async () => {
            try {
                const r = await apiClient.get(`/pharmacy/dispense/${dispenseId}/payment-status`);
                setPollStatus(r.data);
                if (r.data?.invoice_status === 'Paid' || r.data?.mpesa_status === 'Success') {
                    clearInterval(interval);
                    toast.success(`M-Pesa receipt ${r.data?.mpesa_receipt_number || ''} confirmed.`);
                    onSettled();
                } else if (r.data?.mpesa_status === 'Failed') {
                    clearInterval(interval);
                    toast.error(r.data?.mpesa_result_desc || 'M-Pesa payment failed.');
                    setPollingTxnId(null);
                } else if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
                    clearInterval(interval);
                    toast.error('M-Pesa did not confirm in time. Check Cashier > M-Pesa transactions.');
                    setPollingTxnId(null);
                }
            } catch {
                // Transient — keep polling until timeout.
            }
        }, POLL_MS);
        return () => clearInterval(interval);
    }, [pollingTxnId, dispenseId, onSettled]);

    const submit = async () => {
        const amt = Number(amount);
        if (!amt || amt <= 0) return toast.error('Enter a valid amount.');
        if (method === 'mpesa' && !phone) return toast.error('M-Pesa needs a phone number.');

        setSubmitting(true);
        try {
            const payload = {
                method,
                amount: amt,
                phone_number: method === 'mpesa' ? phone : null,
                transaction_reference: reference || null,
            };
            const res = await apiClient.post(`/pharmacy/dispense/${dispenseId}/pay`, payload);

            if (method === 'cash') {
                toast.success(`Cash payment recorded. Invoice ${res.data?.invoice_status}.`);
                onSettled();
            } else if (method === 'mpesa') {
                toast.success('STK push sent. Customer to confirm on their phone.');
                setPollingTxnId(res.data?.mpesa_transaction_id);
            }
        } catch (err) {
            toast.error(err?.response?.data?.detail || 'Payment failed.');
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-ink-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-elevated w-full max-w-md">
                <div className="flex items-center justify-between p-4 border-b border-ink-100">
                    <div>
                        <h3 className="text-sm font-semibold text-ink-900">Collect payment</h3>
                        <p className="text-xs text-ink-500">
                            {patientName ? `${patientName} · ` : ''}Invoice #{invoiceId} · KES {Number(amountDue || 0).toLocaleString()}
                        </p>
                    </div>
                    <button onClick={onClose} className="text-ink-400 hover:text-ink-700" aria-label="Close">
                        <XIcon size={18} />
                    </button>
                </div>

                <div className="p-5 space-y-4">
                    {pollingTxnId ? (
                        <div className="text-center py-6">
                            <Smartphone size={32} className="mx-auto text-brand-700 mb-2" />
                            <p className="text-sm text-ink-700 font-medium">Waiting for M-Pesa confirmation…</p>
                            <p className="text-xs text-ink-500 mt-1">Customer should accept the STK push on their phone.</p>
                            {pollStatus?.mpesa_status && (
                                <p className="text-xs mt-3 font-mono">status: {pollStatus.mpesa_status}</p>
                            )}
                        </div>
                    ) : (
                        <>
                            <div className="flex gap-2 border-b border-ink-100">
                                <button onClick={() => setMethod('cash')}
                                        className={'flex items-center gap-2 px-3 py-2 text-sm font-medium border-b-2 -mb-px ' +
                                            (method === 'cash' ? 'border-brand-600 text-brand-700' : 'border-transparent text-ink-500')}>
                                    <Banknote size={14} /> Cash
                                </button>
                                <button onClick={() => setMethod('mpesa')}
                                        className={'flex items-center gap-2 px-3 py-2 text-sm font-medium border-b-2 -mb-px ' +
                                            (method === 'mpesa' ? 'border-brand-600 text-brand-700' : 'border-transparent text-ink-500')}>
                                    <Smartphone size={14} /> M-Pesa
                                </button>
                                <button disabled
                                        className="flex items-center gap-2 px-3 py-2 text-sm font-medium border-b-2 -mb-px border-transparent text-ink-300 cursor-not-allowed"
                                        title="Card integration coming soon">
                                    <CreditCard size={14} /> Card
                                </button>
                            </div>

                            <label className="block">
                                <span className="block text-xs font-medium text-ink-600 mb-1">Amount</span>
                                <input type="number" step="0.01" className="input" value={amount}
                                       onChange={(e) => setAmount(e.target.value)} />
                            </label>

                            {method === 'mpesa' && (
                                <label className="block">
                                    <span className="block text-xs font-medium text-ink-600 mb-1">Phone number</span>
                                    <input className="input" value={phone}
                                           onChange={(e) => setPhone(e.target.value)}
                                           placeholder="07XXXXXXXX or 2547XXXXXXXX" />
                                </label>
                            )}

                            <label className="block">
                                <span className="block text-xs font-medium text-ink-600 mb-1">
                                    Reference (optional)
                                </span>
                                <input className="input" value={reference}
                                       onChange={(e) => setReference(e.target.value)}
                                       placeholder="Receipt no., notes, etc." />
                            </label>

                            <div className="flex justify-end gap-2 pt-2">
                                <button onClick={onClose}
                                        className="px-3 py-2 rounded-lg border border-ink-200 text-sm font-medium hover:bg-ink-50">
                                    Cancel
                                </button>
                                <button onClick={submit} disabled={submitting}
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