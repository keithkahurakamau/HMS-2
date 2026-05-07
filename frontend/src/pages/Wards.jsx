import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
    Bed, Activity, Search, Filter, UserPlus,
    LogOut, Pill, FileText, AlertCircle, X, Package, Plus, Trash2, CheckCircle2, Printer
} from 'lucide-react';
import toast from 'react-hot-toast';
import { printAdmissionSlip } from '../utils/printTemplates';

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
            
            const patResponse = await apiClient.get('/patients/');
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

    const [clinicalNote, setClinicalNote] = useState('');
    const [isSavingNote, setIsSavingNote] = useState(false);

    const handleSaveClinicalNote = async () => {
        if (!activeBed?.admission_id || !clinicalNote.trim()) {
            toast.error('Type an observation first.');
            return;
        }
        setIsSavingNote(true);
        try {
            await apiClient.post(`/wards/admissions/${activeBed.admission_id}/notes`, {
                note: clinicalNote.trim(),
            });
            toast.success('Observation logged to audit trail.');
            setClinicalNote('');
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Could not save observation.');
        } finally {
            setIsSavingNote(false);
        }
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
                    <span className="section-eyebrow">Inpatient</span>
                    <h1 className="section-title mt-1">Ward &amp; Bed Management</h1>
                    <p className="section-sub">Monitor hospital capacity, manage admissions, and track clinical inventory.</p>
                </div>
                <button onClick={() => setIsAdmitModalOpen(true)} className="btn-primary">
                    <UserPlus size={16} /> Admit patient
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="stat-tile">
                    <div className="flex justify-between items-start">
                        <div className="stat-icon bg-blue-50 ring-blue-100 text-blue-600"><Activity size={20} /></div>
                    </div>
                    <div>
                        <h3 className="stat-label">Total occupancy</h3>
                        <div className="flex items-baseline gap-2 mt-1">
                            <p className="stat-value">{occupancyRate}%</p>
                            <p className="text-sm font-medium text-ink-500">({occupiedBeds} / {totalBeds})</p>
                        </div>
                    </div>
                </div>
                <div className="stat-tile">
                    <div className="flex justify-between items-start">
                        <div className="stat-icon bg-accent-50 ring-accent-100 text-accent-600"><Bed size={20} /></div>
                    </div>
                    <div>
                        <h3 className="stat-label">Available capacity</h3>
                        <p className="stat-value mt-1 text-accent-700">{availableBeds}</p>
                    </div>
                </div>
                <div className="stat-tile">
                    <div className="flex justify-between items-start">
                        <div className="stat-icon bg-amber-50 ring-amber-100 text-amber-600"><AlertCircle size={20} /></div>
                    </div>
                    <div>
                        <h3 className="stat-label">Sanitation / maintenance</h3>
                        <p className="stat-value mt-1 text-amber-700">{totalBeds - occupiedBeds - availableBeds}</p>
                    </div>
                </div>
            </div>

            {/* BED BOARD GRID */}
            <div className="space-y-6">
                {isLoading ? (
                    <div className="card text-center py-12 text-ink-400"><Activity className="animate-spin mx-auto mb-2" size={20} /> Resolving allocations…</div>
                ) : wards.map(ward => (
                    <div key={ward.id} className="card overflow-hidden">
                        <div className="bg-ink-50/60 border-b border-ink-100 p-4 flex justify-between items-center">
                            <h2 className="text-base font-semibold text-ink-900 tracking-tight">{ward.name}</h2>
                            <span className="text-xs font-medium text-ink-500">Capacity limit: <span className="text-ink-800 font-semibold">{ward.capacity}</span></span>
                        </div>

                        <div className="p-5 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                            {ward.beds.map(bed => {
                                const variantBg = {
                                    Available: 'bg-white border-accent-200',
                                    Occupied:  'bg-blue-50/60 border-blue-200 hover:border-blue-400 cursor-pointer hover:-translate-y-0.5',
                                    Cleaning:  'bg-purple-50 border-purple-200',
                                }[bed.status] || 'bg-amber-50 border-amber-200';
                                const dotBg = {
                                    Available: 'bg-accent-500',
                                    Occupied:  'bg-blue-500 animate-pulse-soft',
                                    Cleaning:  'bg-purple-500',
                                }[bed.status] || 'bg-amber-500';
                                const txt = {
                                    Available: 'text-accent-700',
                                    Cleaning:  'text-purple-700',
                                }[bed.status] || 'text-amber-700';
                                return (
                                    <button key={bed.id} type="button"
                                        onClick={() => bed.status === 'Occupied' ? setActiveBed({ ...bed, wardName: ward.name }) : null}
                                        className={`relative text-left flex flex-col p-3.5 rounded-xl border transition-all duration-150 ${variantBg}`}>
                                        <span className={`absolute top-3 right-3 w-2 h-2 rounded-full ${dotBg}`} />
                                        <div className="flex items-center gap-2 mb-2">
                                            <Bed size={16} className={bed.status === 'Occupied' ? 'text-blue-600' : 'text-ink-400'} />
                                            <span className="font-semibold text-ink-900 text-sm">{bed.number}</span>
                                        </div>
                                        {bed.status === 'Occupied' ? (
                                            <div className="flex-1 flex flex-col justify-between">
                                                <div>
                                                    <p className="text-xs font-semibold text-ink-900 line-clamp-1">{bed.patient}</p>
                                                    <p className="text-2xs font-medium text-blue-700 mt-1 line-clamp-1">{bed.diagnosis}</p>
                                                </div>
                                                <p className="text-2xs font-semibold text-ink-400 uppercase tracking-wider mt-2">Init: {bed.admission_date}</p>
                                            </div>
                                        ) : (
                                            <div className="flex-1 flex items-center justify-center">
                                                <p className={`text-xs font-semibold ${txt}`}>{bed.status}</p>
                                            </div>
                                        )}
                                    </button>
                                );
                            })}
                        </div>
                    </div>
                ))}
            </div>

            {/* ADMISSION MODAL */}
            {isAdmitModalOpen && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <div className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setIsAdmitModalOpen(false)}></div>
                    <div className="relative w-full max-w-md bg-white h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="p-6 border-b border-ink-100 bg-gradient-to-br from-brand-600 to-brand-700 text-white shrink-0">
                            <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-brand-200">New admission</span>
                            <h2 className="text-lg font-semibold mt-1 flex items-center gap-2"><UserPlus size={20} className="text-brand-200" /> Admit patient</h2>
                            <p className="text-sm text-brand-100/90 mt-1">Allocate a bed and create a new inpatient admission record.</p>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 sm:p-6 bg-ink-50/40 custom-scrollbar">
                            <form id="admitForm" onSubmit={handleAdmit}>
                                <div className="card p-5 space-y-4">
                                    <div>
                                        <label className="label">Select patient</label>
                                        <select required value={admitForm.patient_id} onChange={(e) => setAdmitForm({...admitForm, patient_id: e.target.value})} className="input">
                                            <option value="">Choose a registered patient…</option>
                                            {patients.map(p => (
                                                <option key={p.patient_id} value={p.patient_id}>
                                                    {p.surname}, {p.other_names} ({p.outpatient_no})
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="label">Select available bed</label>
                                        <select required value={admitForm.bed_id} onChange={(e) => setAdmitForm({...admitForm, bed_id: e.target.value})} className="input">
                                            <option value="">Assign a bed…</option>
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
                                        <label className="label">Primary diagnosis (reason for admission)</label>
                                        <input required type="text" value={admitForm.diagnosis} onChange={(e) => setAdmitForm({...admitForm, diagnosis: e.target.value})} className="input" placeholder="e.g. Severe Malaria" />
                                    </div>
                                </div>
                            </form>
                        </div>

                        <div className="p-5 border-t border-ink-100 bg-white flex gap-3 shrink-0">
                            <button type="button" onClick={() => setIsAdmitModalOpen(false)} className="btn-secondary">Cancel</button>
                            <button type="submit" form="admitForm" className="btn-primary flex-1">Allocate &amp; admit</button>
                        </div>
                    </div>
                </div>
            )}

            {/* SLIDE-OVER: INPATIENT CHART & AUDIT INVENTORY */}
            {activeBed && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <div className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setActiveBed(null)}></div>
                    <div className="relative w-full max-w-2xl bg-white h-full shadow-elevated flex flex-col animate-slide-in-right">

                        <div className="p-6 border-b border-ink-100 bg-gradient-to-br from-blue-600 to-blue-700 text-white shrink-0">
                            <div className="flex justify-between items-start">
                                <div>
                                    <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-blue-200">Inpatient chart</span>
                                    <h2 className="text-xl font-semibold mt-1 tracking-tight">{activeBed.patient}</h2>
                                    <p className="text-sm text-blue-100/90 mt-1 font-medium">{activeBed.wardName} &middot; Bed {activeBed.number}</p>
                                </div>
                                <button onClick={() => {setActiveBed(null); setCart([]);}} aria-label="Close" className="text-blue-100 hover:text-white p-2 hover:bg-white/10 rounded-lg"><X size={18}/></button>
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-5 bg-ink-50/40 custom-scrollbar">

                            <div className="card-flush p-5 border-l-4 border-l-accent-500">
                                <h3 className="section-eyebrow mb-4 border-b border-ink-100 pb-3 flex items-center gap-2">
                                    <Package size={16} className="text-accent-600" /> Administer ward inventory
                                </h3>

                                <div className="flex flex-wrap gap-2 mb-4">
                                    <select value={selectedBatchId} onChange={(e) => setSelectedBatchId(e.target.value)} className="input flex-1 min-w-[12rem]">
                                        <option value="">Select available ward stock…</option>
                                        {wardInventory.map(item => (
                                            <option key={item.batch_id} value={item.batch_id}>
                                                {item.name} (Batch {item.batch_number}) – {item.quantity} available
                                            </option>
                                        ))}
                                    </select>
                                    <input type="number" min="1" placeholder="Qty" value={consumeQty} onChange={(e) => setConsumeQty(e.target.value)} className="input w-20" />
                                    <button onClick={handleAddToCart} className="btn bg-ink-100 text-ink-800 hover:bg-ink-200">
                                        <Plus size={15} /> Add
                                    </button>
                                </div>

                                {cart.length > 0 && (
                                    <div className="mb-4 card-flush overflow-x-auto">
                                        <table className="table-clean min-w-[400px]">
                                            <thead>
                                                <tr>
                                                    <th>Item to administer</th>
                                                    <th>Qty</th>
                                                    <th></th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {cart.map(item => (
                                                    <tr key={item.batch_id}>
                                                        <td className="font-medium">{item.name} <span className="text-2xs text-ink-400 block">{item.batch_number}</span></td>
                                                        <td className="font-semibold">{item.qty}</td>
                                                        <td className="text-right">
                                                            <button onClick={() => setCart(cart.filter(c => c.batch_id !== item.batch_id))} aria-label="Remove" className="text-ink-400 hover:text-rose-600"><Trash2 size={15}/></button>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}

                                <button onClick={handleConsumeStock} disabled={cart.length === 0 || isConsuming} className="btn-success w-full">
                                    <CheckCircle2 size={16} /> {isConsuming ? 'Processing…' : 'Administer & log to audit trail'}
                                </button>
                            </div>

                            <div className="card-flush p-5">
                                <h3 className="section-eyebrow mb-4 border-b border-ink-100 pb-3">Clinical log</h3>
                                <textarea
                                    rows="3"
                                    value={clinicalNote}
                                    onChange={(e) => setClinicalNote(e.target.value)}
                                    className="input resize-none mb-3"
                                    placeholder="Append observation parameters… (e.g. vitals, medication response, mood)"
                                />
                                <button onClick={handleSaveClinicalNote} disabled={isSavingNote || !clinicalNote.trim()} className="btn bg-ink-800 text-white hover:bg-ink-900 w-full disabled:opacity-50 disabled:cursor-not-allowed">
                                    {isSavingNote ? 'Saving…' : 'Commit observation'}
                                </button>
                            </div>
                        </div>

                        <div className="p-5 border-t border-ink-100 bg-white shrink-0 space-y-2">
                            <button
                                onClick={() => printAdmissionSlip({
                                    patient: { full_name: activeBed.patient, outpatient_no: activeBed.op_no, inpatient_no: activeBed.inpatient_no, age: activeBed.age, sex: activeBed.sex, blood_group: activeBed.blood_group },
                                    admission: {
                                        admission_id: activeBed.admission_id,
                                        ward_name: activeBed.wardName,
                                        bed_number: activeBed.number,
                                        admission_date: activeBed.admission_date,
                                        primary_diagnosis: activeBed.diagnosis,
                                        status: 'Active',
                                    },
                                    doctor: { full_name: activeBed.doctor },
                                })}
                                className="btn-secondary w-full"
                            >
                                <Printer size={15} /> Print admission slip
                            </button>
                            <button onClick={handleDischarge} className="btn-danger w-full bg-rose-50 text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100 shadow-none">
                                <LogOut size={16} /> Execute discharge protocol
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}