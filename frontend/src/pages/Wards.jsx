import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { 
    Bed, Activity, Search, Filter, UserPlus, 
    LogOut, Pill, FileText, AlertCircle, X, Package, Plus, Trash2, CheckCircle2
} from 'lucide-react';
import toast from 'react-hot-toast';

export default function Wards() {
    const [wards, setWards] = useState([]);
    const [wardInventory, setWardInventory] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [patients, setPatients] = useState([]);
    
    // UI Modals & Target Entities
    const [activeBed, setActiveBed] = useState(null); 
    const [isAdmitModalOpen, setIsAdmitModalOpen] = useState(false);
    
    // Data Mutation Payloads
    const [admitForm, setAdmitForm] = useState({ patient_id: '', bed_id: '', diagnosis: '' });
    
    // Inventory Consumption State
    const [cart, setCart] = useState([]);
    const [selectedBatchId, setSelectedBatchId] = useState('');
    const [consumeQty, setConsumeQty] = useState('');
    const [isConsuming, setIsConsuming] = useState(false);

    // --- DATA FETCHING ---
    const fetchBedBoard = async () => {
        setIsLoading(true);
        try {
            const response = await apiClient.get('/wards/board');
            setWards(response.data || []);
            
            const invResponse = await apiClient.get('/wards/inventory');
            setWardInventory(invResponse.data || []);
            
            const patResponse = await apiClient.get('/patients');
            setPatients(patResponse.data || []);
        } catch (error) {
            toast.error("Network Exception: Failed to load Ward data.");
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchBedBoard();
    }, []);

    // --- KPIs ---
    const totalBeds = wards.reduce((sum, ward) => sum + ward.beds.length, 0);
    const occupiedBeds = wards.reduce((sum, ward) => sum + ward.beds.filter(b => b.status === 'Occupied').length, 0);
    const availableBeds = wards.reduce((sum, ward) => sum + ward.beds.filter(b => b.status === 'Available').length, 0);
    const occupancyRate = totalBeds > 0 ? ((occupiedBeds / totalBeds) * 100).toFixed(0) : 0;

    // --- ADMISSION & DISCHARGE HANDLERS ---
    const handleAdmit = async (e) => {
        e.preventDefault();
        try {
            await apiClient.post('/wards/admit', admitForm);
            toast.success("Patient admission transaction completed.");
            setIsAdmitModalOpen(false);
            setAdmitForm({ patient_id: '', bed_id: '', diagnosis: '' });
            fetchBedBoard(); 
        } catch (error) {
            toast.error(error.response?.data?.detail || "Admission transaction failed.");
        }
    };

    const handleDischarge = async () => {
        if (!window.confirm(`Confirm medical discharge protocol for patient: ${activeBed.patient}?`)) return;
        try {
            await apiClient.post(`/wards/discharge/${activeBed.admission_id}`, { notes: "Standard Protocol Discharge" });
            toast.success("Discharge transaction completed. Bed matrix updated to cleaning state.");
            setActiveBed(null);
            fetchBedBoard(); 
        } catch (error) {
            toast.error("Discharge transaction failed.");
        }
    };

    // --- WARD INVENTORY HANDLERS ---
    const handleAddToCart = () => {
        if (!selectedBatchId || !consumeQty || consumeQty <= 0) return;
        
        const item = wardInventory.find(i => i.batch_id === parseInt(selectedBatchId));
        if (!item) return;

        if (parseInt(consumeQty) > item.quantity) {
            return toast.error(`Stock violation: Only ${item.quantity} available in this batch.`);
        }

        setCart(prev => {
            const existing = prev.find(c => c.batch_id === item.batch_id);
            if (existing) {
                return prev.map(c => c.batch_id === item.batch_id ? { ...c, qty: c.qty + parseInt(consumeQty) } : c);
            }
            return [...prev, { ...item, qty: parseInt(consumeQty) }];
        });
        
        setSelectedBatchId('');
        setConsumeQty('');
    };

    const handleConsumeStock = async () => {
        if (cart.length === 0) return;
        setIsConsuming(true);
        try {
            const payload = {
                items: cart.map(c => ({ batch_id: c.batch_id, quantity: c.qty })),
                notes: "Administered by Ward Nurse"
            };
            
            await apiClient.post(`/wards/${activeBed.admission_id}/consume`, payload);
            toast.success("Stock successfully deducted and added to audit trail.");
            
            setCart([]);
            fetchBedBoard(); // Refresh local stock levels
        } catch (error) {
            toast.error(error.response?.data?.detail || "Stock consumption failed.");
        } finally {
            setIsConsuming(false);
        }
    };

    return (
        <div className="space-y-6 pb-8">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Ward & Bed Management</h1>
                    <p className="text-sm text-slate-500 mt-1">Monitor hospital capacity, manage admissions, and track clinical inventory.</p>
                </div>
                <div className="flex gap-3">
                    <button onClick={() => setIsAdmitModalOpen(true)} className="inline-flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white px-4 py-2.5 rounded-lg text-sm font-bold transition-colors shadow-sm">
                        <UserPlus size={18} /> Admit Patient
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
                    <div>
                        <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Total Occupancy</p>
                        <div className="flex items-baseline gap-2">
                            <p className="text-2xl font-black text-slate-900">{occupancyRate}%</p>
                            <p className="text-sm font-medium text-slate-500">({occupiedBeds} / {totalBeds})</p>
                        </div>
                    </div>
                    <div className="w-12 h-12 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center"><Activity size={24} /></div>
                </div>
                <div className="bg-white p-5 rounded-xl border border-green-200 shadow-sm flex items-center justify-between">
                    <div>
                        <p className="text-xs font-bold text-green-600 uppercase tracking-wider mb-1">Available Capacity</p>
                        <p className="text-2xl font-black text-green-700">{availableBeds}</p>
                    </div>
                    <div className="w-12 h-12 bg-green-100 text-green-600 rounded-full flex items-center justify-center"><Bed size={24} /></div>
                </div>
                <div className="bg-white p-5 rounded-xl border border-orange-200 shadow-sm flex items-center justify-between">
                    <div>
                        <p className="text-xs font-bold text-orange-600 uppercase tracking-wider mb-1">Sanitation / Maintenance</p>
                        <p className="text-2xl font-black text-orange-700">{totalBeds - occupiedBeds - availableBeds}</p>
                    </div>
                    <div className="w-12 h-12 bg-orange-100 text-orange-600 rounded-full flex items-center justify-center animate-pulse"><AlertCircle size={24} /></div>
                </div>
            </div>

            {/* BED BOARD GRID */}
            <div className="space-y-8">
                {isLoading ? (
                    <div className="text-center py-12 text-slate-400"><Activity className="animate-spin mx-auto mb-2" /> Resolving allocations...</div>
                ) : wards.map(ward => (
                    <div key={ward.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                        <div className="bg-slate-50 border-b border-slate-100 p-4 flex justify-between items-center">
                            <h2 className="text-lg font-bold text-slate-800">{ward.name}</h2>
                            <span className="text-sm font-semibold text-slate-500">Capacity limit: {ward.capacity}</span>
                        </div>
                        
                        <div className="p-6 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-4">
                            {ward.beds.map(bed => (
                                <div 
                                    key={bed.id} 
                                    onClick={() => bed.status === 'Occupied' ? setActiveBed({ ...bed, wardName: ward.name }) : null}
                                    className={`relative flex flex-col p-4 rounded-xl border-2 transition-all ${
                                        bed.status === 'Available' ? 'bg-white border-green-200' :
                                        bed.status === 'Occupied' ? 'bg-blue-50 border-blue-300 hover:border-blue-500 cursor-pointer shadow-sm' :
                                        bed.status === 'Cleaning' ? 'bg-purple-50 border-purple-200' :
                                        'bg-orange-50 border-orange-200' 
                                    }`}
                                >
                                    <div className={`absolute top-3 right-3 w-3 h-3 rounded-full ${
                                        bed.status === 'Available' ? 'bg-green-500' :
                                        bed.status === 'Occupied' ? 'bg-blue-500 animate-pulse' :
                                        bed.status === 'Cleaning' ? 'bg-purple-500' : 'bg-orange-500'
                                    }`}></div>

                                    <div className="flex items-center gap-2 mb-3">
                                        <Bed size={20} className={bed.status === 'Occupied' ? 'text-blue-600' : 'text-slate-400'} />
                                        <span className="font-bold text-slate-800">{bed.number}</span>
                                    </div>

                                    {bed.status === 'Occupied' ? (
                                        <div className="flex-1 flex flex-col justify-between">
                                            <div>
                                                <p className="text-sm font-bold text-slate-900 line-clamp-1">{bed.patient}</p>
                                                <p className="text-xs font-semibold text-blue-700 mt-1 line-clamp-1">{bed.diagnosis}</p>
                                            </div>
                                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mt-3">Init: {bed.admission_date}</p>
                                        </div>
                                    ) : (
                                        <div className="flex-1 flex flex-col justify-center items-center">
                                            <p className={`text-sm font-bold ${
                                                bed.status === 'Available' ? 'text-green-600' : 
                                                bed.status === 'Cleaning' ? 'text-purple-600' : 'text-orange-600'
                                            }`}>{bed.status}</p>
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </div>

            {/* ADMISSION MODAL */}
            {isAdmitModalOpen && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setIsAdmitModalOpen(false)}></div>
                    <div className="relative w-full max-w-md bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right">
                        <div className="p-6 border-b border-slate-100 bg-brand-700 text-white shrink-0">
                            <h2 className="text-xl font-bold flex items-center gap-2"><UserPlus size={24} className="text-brand-200" /> Admit Patient</h2>
                            <p className="text-sm text-brand-100 mt-1">Allocate a bed and create a new inpatient admission record.</p>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50">
                            <form id="admitForm" onSubmit={handleAdmit} className="space-y-6">
                                <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-4">
                                    <div>
                                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Select Patient</label>
                                        <select required value={admitForm.patient_id} onChange={(e) => setAdmitForm({...admitForm, patient_id: e.target.value})} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none">
                                            <option value="">Choose a registered patient...</option>
                                            {patients.map(p => (
                                                <option key={p.patient_id} value={p.patient_id}>
                                                    {p.surname}, {p.other_names} ({p.outpatient_no})
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Select Available Bed</label>
                                        <select required value={admitForm.bed_id} onChange={(e) => setAdmitForm({...admitForm, bed_id: e.target.value})} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none">
                                            <option value="">Assign a bed...</option>
                                            {wards.map(ward => (
                                                <optgroup key={ward.id} label={ward.name}>
                                                    {ward.beds.filter(b => b.status === 'Available').map(bed => (
                                                        <option key={bed.id} value={bed.id}>Bed {bed.number}</option>
                                                    ))}
                                                </optgroup>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Primary Diagnosis (Reason for Admission)</label>
                                        <input required type="text" value={admitForm.diagnosis} onChange={(e) => setAdmitForm({...admitForm, diagnosis: e.target.value})} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" placeholder="e.g. Severe Malaria" />
                                    </div>
                                </div>
                            </form>
                        </div>

                        <div className="p-6 border-t border-slate-200 bg-white flex gap-3 shrink-0">
                            <button type="button" onClick={() => setIsAdmitModalOpen(false)} className="px-6 py-2.5 border border-slate-300 text-slate-700 rounded-lg font-bold hover:bg-slate-50 w-1/3 transition-colors">Cancel</button>
                            <button type="submit" form="admitForm" className="flex-1 bg-brand-600 hover:bg-brand-700 text-white py-2.5 rounded-lg font-bold shadow-sm flex items-center justify-center gap-2 transition-colors">
                                Allocate & Admit
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* SLIDE-OVER: INPATIENT CHART & AUDIT INVENTORY */}
            {activeBed && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setActiveBed(null)}></div>
                    <div className="relative w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right">
                        
                        <div className="p-6 border-b border-slate-100 bg-blue-600 text-white shrink-0">
                            <div className="flex justify-between items-start mb-4">
                                <div>
                                    <h2 className="text-2xl font-bold">{activeBed.patient}</h2>
                                    <p className="text-blue-200 mt-1 font-medium">{activeBed.wardName} • Vector {activeBed.number}</p>
                                </div>
                                <button onClick={() => {setActiveBed(null); setCart([]);}} className="text-blue-200 hover:text-white p-1 bg-blue-700 rounded-full"><X size={20}/></button>
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50">
                            
                            {/* WARD INVENTORY CONSUMPTION TRACKER */}
                            <div className="bg-white border-l-4 border-accent-500 rounded-r-xl border-y border-r border-slate-200 p-5 shadow-sm">
                                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 flex items-center gap-2 border-b border-slate-100 pb-2">
                                    <Package size={18} className="text-accent-600" /> Administer Ward Inventory
                                </h3>
                                
                                <div className="flex gap-2 mb-4">
                                    <select 
                                        value={selectedBatchId} 
                                        onChange={(e) => setSelectedBatchId(e.target.value)}
                                        className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500"
                                    >
                                        <option value="">Select available ward stock...</option>
                                        {wardInventory.map(item => (
                                            <option key={item.batch_id} value={item.batch_id}>
                                                {item.name} (Batch {item.batch_number}) - {item.quantity} available
                                            </option>
                                        ))}
                                    </select>
                                    <input 
                                        type="number" min="1" placeholder="Qty" 
                                        value={consumeQty} onChange={(e) => setConsumeQty(e.target.value)}
                                        className="w-20 px-3 py-2 border border-slate-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500" 
                                    />
                                    <button onClick={handleAddToCart} className="bg-slate-200 text-slate-800 px-4 py-2 rounded-lg text-sm font-bold hover:bg-slate-300 flex items-center gap-1 transition-colors">
                                        <Plus size={16}/> Add
                                    </button>
                                </div>

                                {cart.length > 0 && (
                                    <div className="mb-4 bg-slate-50 border border-slate-200 rounded-lg overflow-hidden">
                                        <table className="w-full text-left text-sm text-slate-600">
                                            <thead className="bg-white border-b border-slate-200 text-xs uppercase font-bold">
                                                <tr>
                                                    <th className="px-4 py-2">Item to Administer</th>
                                                    <th className="px-4 py-2">Qty</th>
                                                    <th className="px-4 py-2"></th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-slate-100">
                                                {cart.map(item => (
                                                    <tr key={item.batch_id}>
                                                        <td className="px-4 py-2 font-medium">{item.name} <span className="text-[10px] text-slate-400 block">{item.batch_number}</span></td>
                                                        <td className="px-4 py-2 font-bold">{item.qty}</td>
                                                        <td className="px-4 py-2 text-right">
                                                            <button onClick={() => setCart(cart.filter(c => c.batch_id !== item.batch_id))} className="text-slate-400 hover:text-red-500"><Trash2 size={16}/></button>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}

                                <button 
                                    onClick={handleConsumeStock}
                                    disabled={cart.length === 0 || isConsuming}
                                    className="w-full bg-accent-600 text-white py-2.5 rounded-lg text-sm font-bold hover:bg-accent-700 disabled:opacity-50 flex justify-center items-center gap-2 transition-colors"
                                >
                                    <CheckCircle2 size={18} /> {isConsuming ? 'Processing...' : 'Administer & Log to Audit Trail'}
                                </button>
                            </div>

                            {/* Standard Clinical Log */}
                            <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5">
                                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 border-b border-slate-100 pb-2">Clinical Log</h3>
                                <textarea rows="3" className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none mb-3" placeholder="Append observation parameters..."></textarea>
                                <button className="w-full bg-slate-800 text-white py-2 rounded-lg text-sm font-bold hover:bg-slate-900">Commit Block</button>
                            </div>
                        </div>

                        <div className="p-6 border-t border-slate-200 bg-white shrink-0">
                            <button onClick={handleDischarge} className="w-full bg-red-50 border border-red-200 text-red-700 py-3 rounded-lg font-bold flex items-center justify-center gap-2 hover:bg-red-100 transition-colors">
                                <LogOut size={20} /> Execute Discharge Protocol
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}