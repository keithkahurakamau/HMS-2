import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
    Search, Pill, CheckCircle2, AlertCircle, Clock,
    ChevronDown, ChevronUp, Package, Printer, XCircle,
    FileWarning, ShoppingCart, Plus, Minus, Trash2, CreditCard, Store, Activity
} from 'lucide-react';
import toast from 'react-hot-toast';
import { printPrescription } from '../utils/printTemplates';
import PageHeader from '../components/PageHeader';

export default function Pharmacy() {
    // --- APP STATE ---
    const [activeTab, setActiveTab] = useState('rx'); // 'rx' or 'otc'
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
    const generateIdempotencyKey = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    const handleOTCCheckout = async () => {
        if (cart.length === 0) return;
        setIsProcessing(true);
        try {
            const payload = {
                items: cart.map(c => ({
                    batch_id: c.batch_id,
                    item_id: c.item_id,
                    quantity: c.qty,
                    price: c.unit_price
                })),
                idempotency_key: generateIdempotencyKey()
            };

            await apiClient.post('/pharmacy/dispense', payload);
            toast.success(`Payment of KES ${cartTotal.toLocaleString()} received. Stock deducted.`);
            setCart([]);
            fetchPharmacyInventory(); 
        } catch (error) {
            toast.error(error.response?.data?.detail || "Checkout failed");
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
        setIsProcessing(true);
        try {
            const payload = {
                items: [
                    {
                        batch_id: inventory[0]?.batch_id || 1, 
                        item_id: inventory[0]?.item_id || 1,
                        quantity: 1, 
                        price: inventory[0]?.unit_price || 0
                    }
                ],
                patient_id: activeOrder.patient_id,
                record_id: activeOrder.record_id,
                idempotency_key: generateIdempotencyKey()
            };

            await apiClient.post('/pharmacy/dispense', payload);
            toast.success(`Prescription ${activeOrder.id} dispensed & closed!`);
            
            setQueue(queue.filter(q => q.id !== activeOrder.id));
            setActiveOrder(null);
            setIsQueueOpen(true);
            fetchPharmacyInventory(); 
        } catch (error) {
            toast.error(error.response?.data?.detail || "Failed to dispense prescription.");
        } finally {
            setIsProcessing(false);
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
                            <div className="flex justify-between items-center mb-4">
                                <span className="section-eyebrow">Subtotal</span>
                                <span className="text-xl font-semibold text-ink-900 tracking-tight">KES {cartTotal.toLocaleString()}</span>
                            </div>
                            <button onClick={handleOTCCheckout} disabled={cart.length === 0 || isProcessing} className="btn-success w-full py-3">
                                <CreditCard size={16} /> {isProcessing ? 'Processing…' : 'Checkout & dispense'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}