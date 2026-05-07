import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
    Search, Pill, CheckCircle2, AlertCircle, Clock,
    ChevronDown, ChevronUp, Package, Printer, XCircle,
    FileWarning, ShoppingCart, Plus, Minus, Trash2, CreditCard, Store, Activity
} from 'lucide-react';
import toast from 'react-hot-toast';
import { printPrescription } from '../utils/printTemplates';

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
            {/* GLOBAL PHARMACY HEADER & TABS */}
            <div className="bg-white border border-slate-200 rounded-xl p-2 shadow-sm flex items-center justify-between shrink-0">
                <div className="flex bg-slate-100 p-1 rounded-lg w-full max-w-md">
                    <button onClick={() => setActiveTab('rx')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-md text-sm font-bold transition-all ${activeTab === 'rx' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                        <Pill size={18} /> Rx Fulfillment
                    </button>
                    <button onClick={() => setActiveTab('otc')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-md text-sm font-bold transition-all ${activeTab === 'otc' ? 'bg-white text-accent-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                        <Store size={18} /> OTC Point of Sale
                    </button>
                </div>
                <div className="text-right px-4 text-sm font-semibold text-slate-500">
                    {new Date().toLocaleDateString('en-KE', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                </div>
            </div>

            {/* ========================================= */}
            {/* MODE 1: PRESCRIPTION FULFILLMENT (CLINICAL) */}
            {/* ========================================= */}
            {activeTab === 'rx' && (
                <>
                    <div className="bg-white border border-slate-200 rounded-xl shadow-sm shrink-0 flex flex-col z-30">
                        <button onClick={() => setIsQueueOpen(!isQueueOpen)} className="w-full p-4 flex justify-between items-center bg-slate-50 hover:bg-brand-50 transition-colors rounded-t-xl focus:outline-none">
                            <div className="flex items-center gap-3">
                                <Package className="text-brand-600" size={20} />
                                <h2 className="font-bold text-slate-800 text-lg">Pending Prescriptions</h2>
                                <span className="bg-orange-100 text-orange-700 text-xs font-bold px-2.5 py-1 rounded-full">{queue.length} Awaiting</span>
                            </div>
                            <div className="flex items-center gap-2 text-slate-500 text-sm font-medium">
                                {isQueueOpen ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                            </div>
                        </button>

                        {isQueueOpen && (
                            <div className="border-t border-slate-100 p-4 bg-white rounded-b-xl">
                                {isLoadingQueue ? (
                                    <div className="text-center py-8 text-slate-400">
                                        <Activity className="animate-spin mx-auto mb-2 text-brand-500" size={24} />
                                        Syncing prescription queue...
                                    </div>
                                ) : queue.length === 0 ? (
                                    <div className="text-center py-8 text-slate-400">No pending prescriptions at this time.</div>
                                ) : (
                                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                        {queue.map((order) => (
                                            <div key={order.id} onClick={() => {setActiveOrder(order); setIsQueueOpen(false);}} className={`p-3 rounded-lg border cursor-pointer transition-all ${activeOrder?.id === order.id ? 'bg-brand-50 border-brand-500 shadow-sm ring-1 ring-brand-500' : 'bg-white hover:border-brand-300'}`}>
                                                <div className="flex justify-between items-start mb-2">
                                                    <h3 className="font-semibold text-sm text-slate-900">{order.patient}</h3>
                                                    {order.priority === 'High' && <AlertCircle size={14} className="text-red-500 animate-pulse" />}
                                                </div>
                                                <div className="flex justify-between items-center text-xs text-slate-500 mb-1"><span className="font-medium text-brand-700">{order.id}</span></div>
                                                <div className="flex justify-between items-center text-xs text-slate-400"><span>{order.doctor}</span><span className="bg-slate-100 px-2 py-0.5 rounded text-slate-600 flex items-center gap-1"><Clock size={10} /> {order.time}</span></div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col z-10 relative">
                        {!activeOrder ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-slate-400 bg-slate-50/50">
                                <Pill size={64} className="mb-4 text-slate-300" strokeWidth={1.5} />
                                <h3 className="text-lg font-semibold text-slate-600 mb-1">Select an Order</h3>
                            </div>
                        ) : (
                            <>
                                <div className="shrink-0 flex flex-col">
                                    <div className="p-4 border-b border-slate-200 bg-white flex justify-between items-center shadow-[0_2px_4px_rgba(0,0,0,0.02)] z-10">
                                        <div className="flex items-center gap-4">
                                            <div className="w-12 h-12 bg-slate-100 text-slate-600 rounded-full flex items-center justify-center font-bold text-lg border border-slate-200"><FileWarning size={20} /></div>
                                            <div>
                                                <h1 className="text-xl font-bold text-slate-900">Rx: {activeOrder.id}</h1>
                                                <p className="text-sm font-medium text-slate-500">{activeOrder.patient} • {activeOrder.op_no} • {activeOrder.doctor}</p>
                                            </div>
                                        </div>
                                        {activeOrder.allergies && (
                                            <div className="bg-red-50 border border-red-200 px-4 py-2 rounded-lg flex items-center gap-3 animate-pulse">
                                                <AlertCircle size={24} className="text-red-600" />
                                                <div>
                                                    <p className="text-xs font-bold text-red-800 uppercase tracking-wider">Allergies</p>
                                                    <p className="text-sm font-bold text-red-600">{activeOrder.allergies}</p>
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                </div>

                                <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-slate-50/50">
                                    {activeOrder.prescriptions?.map((med, idx) => (
                                        <div key={idx} className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
                                            <div className="flex justify-between items-start">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-3 mb-1">
                                                        <h4 className="font-bold text-lg text-slate-900">{med.drug}</h4>
                                                    </div>
                                                    <div className="flex gap-6 mt-3 text-sm text-slate-700">
                                                        <div><span className="block text-xs font-bold text-slate-400 uppercase">Dosage</span>{med.dosage}</div>
                                                        <div><span className="block text-xs font-bold text-slate-400 uppercase">Freq</span>{med.frequency}</div>
                                                        <div><span className="block text-xs font-bold text-slate-400 uppercase">Duration</span>{med.duration}</div>
                                                    </div>
                                                </div>
                                                <div className="flex flex-col gap-2 ml-4 w-40">
                                                    <label className="flex items-center gap-2 text-sm font-medium text-slate-700 cursor-pointer p-2 border border-slate-200 rounded hover:bg-slate-50"><input type="checkbox" className="w-4 h-4 text-brand-600 rounded" /> Packed</label>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div className="p-4 border-t border-slate-200 bg-slate-50 flex justify-end gap-2 shrink-0 z-10 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.02)]">
                                    <button
                                        onClick={() => printPrescription({
                                            patient: { full_name: activeOrder.patient, outpatient_no: activeOrder.op_no, allergies: activeOrder.allergies },
                                            doctor: { full_name: activeOrder.doctor, license_number: activeOrder.doctor_license },
                                            items: (activeOrder.prescriptions || []).map(p => ({ drug_name: p.drug, dosage: p.dosage, frequency: p.frequency, duration: p.duration, route: p.route || p.notes })),
                                            notes: activeOrder.clinical_notes,
                                            recordId: activeOrder.id,
                                        })}
                                        className="px-4 py-2 bg-white border border-slate-200 text-slate-700 rounded-lg text-sm font-semibold hover:bg-slate-50 flex items-center gap-2"
                                    >
                                        <Printer size={16}/> Print Rx
                                    </button>
                                    <button onClick={handleReturnToDoctor} className="px-4 py-2 bg-white border border-red-200 text-red-600 rounded-lg text-sm font-semibold hover:bg-red-50 flex items-center gap-2"><XCircle size={16}/> Return to Doctor</button>
                                    <button onClick={handleRxDispense} disabled={isProcessing} className="px-6 py-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded-lg text-sm font-bold flex items-center gap-2 shadow-sm">
                                        <CheckCircle2 size={18}/> {isProcessing ? 'Processing...' : 'Dispense & Close'}
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
                    <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col overflow-hidden">
                        <div className="p-4 border-b border-slate-200 bg-slate-50">
                            <div className="relative">
                                <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                                <input 
                                    type="text" 
                                    placeholder="Search pharmacy inventory..." 
                                    value={otcSearch}
                                    onChange={(e) => setOtcSearch(e.target.value)}
                                    className="w-full pl-10 pr-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-accent-500"
                                />
                            </div>
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                            {isLoading ? (
                                <div className="h-full flex flex-col items-center justify-center text-slate-400">
                                    <Activity className="animate-spin mb-2" /> Loading local batches...
                                </div>
                            ) : filteredInventory.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center text-slate-400">
                                    No stock matches your search.
                                </div>
                            ) : (
                                <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                                    {filteredInventory.map(item => (
                                        <div key={item.batch_id} className="border border-slate-200 rounded-lg p-3 hover:border-accent-300 hover:shadow-sm transition-all bg-white flex flex-col justify-between">
                                            <div>
                                                <div className="flex justify-between items-start mb-1">
                                                    <h4 className="font-bold text-sm text-slate-900">{item.name}</h4>
                                                    <span className="text-xs font-semibold bg-slate-100 text-slate-600 px-2 py-0.5 rounded">{item.category}</span>
                                                </div>
                                                <div className="flex items-center gap-2 mt-2">
                                                    <span className="font-bold text-accent-700">KES {item.unit_price}</span>
                                                    <span className="text-slate-300">|</span>
                                                    <span className={`text-xs font-semibold ${item.quantity > 0 ? 'text-slate-500' : 'text-red-500'}`}>Stock: {item.quantity}</span>
                                                </div>
                                                <div className="text-[10px] text-slate-400 mt-1 uppercase tracking-wider">Batch: {item.batch_number}</div>
                                            </div>
                                            <button 
                                                onClick={() => addToCart(item)}
                                                disabled={item.quantity === 0}
                                                className="mt-3 w-full py-1.5 bg-slate-50 border border-slate-200 hover:bg-accent-50 hover:border-accent-300 hover:text-accent-700 text-slate-700 text-sm font-bold rounded flex items-center justify-center gap-1 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                            >
                                                <Plus size={16} /> Add
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* RIGHT PANEL: SHOPPING CART */}
                    <div className="w-full md:w-96 bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col overflow-hidden shrink-0">
                        <div className="p-4 border-b border-slate-200 bg-slate-50 flex justify-between items-center">
                            <h3 className="font-bold text-slate-800 flex items-center gap-2">
                                <ShoppingCart size={18} className="text-accent-600" /> Current Sale
                            </h3>
                            <span className="bg-accent-100 text-accent-800 text-xs font-bold px-2 py-1 rounded-full">{cart.length} Items</span>
                        </div>
                        
                        <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar bg-slate-50/30">
                            {cart.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center text-slate-400 space-y-2">
                                    <ShoppingCart size={48} className="opacity-20" />
                                    <p className="text-sm">Cart is empty</p>
                                </div>
                            ) : (
                                cart.map(item => (
                                    <div key={item.batch_id} className="bg-white border border-slate-200 p-3 rounded-lg shadow-sm">
                                        <div className="flex justify-between items-start mb-2">
                                            <h4 className="font-semibold text-sm text-slate-800 line-clamp-1">{item.name}</h4>
                                            <button onClick={() => removeFromCart(item.batch_id)} className="text-slate-400 hover:text-red-500 transition-colors"><Trash2 size={16}/></button>
                                        </div>
                                        <div className="flex justify-between items-center">
                                            <span className="text-xs font-bold text-slate-500">KES {item.unit_price} x {item.qty}</span>
                                            <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-md p-1">
                                                <button onClick={() => updateQty(item.batch_id, -1)} className="p-0.5 hover:bg-white rounded text-slate-600"><Minus size={14}/></button>
                                                <span className="text-sm font-bold w-6 text-center">{item.qty}</span>
                                                <button onClick={() => updateQty(item.batch_id, 1)} className="p-0.5 hover:bg-white rounded text-slate-600"><Plus size={14}/></button>
                                            </div>
                                        </div>
                                    </div>
                                ))
                            )}
                        </div>

                        <div className="p-4 border-t border-slate-200 bg-white">
                            <div className="flex justify-between items-center mb-4">
                                <span className="text-sm font-bold text-slate-500 uppercase">Subtotal</span>
                                <span className="text-2xl font-black text-slate-900">KES {cartTotal.toLocaleString()}</span>
                            </div>
                            <button 
                                onClick={handleOTCCheckout}
                                disabled={cart.length === 0 || isProcessing}
                                className="w-full py-3 bg-accent-600 hover:bg-accent-700 disabled:opacity-50 text-white font-bold rounded-lg shadow-sm flex items-center justify-center gap-2 transition-colors"
                            >
                                <CreditCard size={18} /> {isProcessing ? 'Processing...' : 'Checkout & Dispense'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}