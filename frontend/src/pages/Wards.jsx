import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
    Bed, Activity, Search, Filter, UserPlus,
    LogOut, Pill, FileText, AlertCircle, X, Package, Plus, Trash2, CheckCircle2, Printer
} from 'lucide-react';
import toast from 'react-hot-toast';
import { printAdmissionSlip } from '../utils/printTemplates';
import PageHeader from '../components/PageHeader';
import DepartmentQueue from '../components/DepartmentQueue';

export default function Wards() {
    const [wards, setWards] = useState([]);
    const [wardInventory, setWardInventory] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [patients, setPatients] = useState([]);
    
    // UI Modals & Target Entities
    const [activeBed, setActiveBed] = useState(null);
    const [isAdmitModalOpen, setIsAdmitModalOpen] = useState(false);
    // Ward/bed setup: create wards, add beds (single or bulk).
    const [isSetupOpen, setIsSetupOpen] = useState(false);
    // A non-occupied bed the user clicked — opens the status/delete sheet
    // (this is also the only way a "Cleaning" bed returns to "Available").
    const [setupBed, setSetupBed] = useState(null);
    
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
            <PageHeader
                eyebrow="Inpatient"
                icon={Bed}
                title="Ward & Bed Management"
                subtitle="Monitor hospital capacity, manage admissions, and track clinical inventory."
                actions={
                    <div className="flex gap-2">
                        <button type="button" onClick={() => setIsSetupOpen(true)} className="btn-secondary cursor-pointer">
                            <Plus size={16} /> Set up ward / beds
                        </button>
                        <button type="button" data-tour="ward-admit" onClick={() => setIsAdmitModalOpen(true)} className="btn-primary cursor-pointer">
                            <UserPlus size={16} /> Admit patient
                        </button>
                    </div>
                }
            />

            {/* ── Routed patients panel ───────────────────────────────────── */}
            <DepartmentQueue department="Wards" title="Patients sent to Wards" />

            <div data-tour="ward-kpis" className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="stat-tile">
                    <div className="flex justify-between items-start">
                        <div className="stat-icon bg-blue-50 dark:bg-blue-500/10 ring-blue-100 dark:ring-blue-500/20 text-blue-600 dark:text-blue-300"><Activity size={20} /></div>
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
                        <div className="stat-icon bg-accent-50 dark:bg-accent-500/10 ring-accent-100 dark:ring-accent-500/20 text-accent-600 dark:text-accent-300"><Bed size={20} /></div>
                    </div>
                    <div>
                        <h3 className="stat-label">Available capacity</h3>
                        <p className="stat-value mt-1 text-accent-700 dark:text-accent-300">{availableBeds}</p>
                    </div>
                </div>
                <div className="stat-tile">
                    <div className="flex justify-between items-start">
                        <div className="stat-icon bg-amber-50 dark:bg-amber-500/10 ring-amber-100 dark:ring-amber-500/20 text-amber-600 dark:text-amber-300"><AlertCircle size={20} /></div>
                    </div>
                    <div>
                        <h3 className="stat-label">Sanitation / maintenance</h3>
                        <p className="stat-value mt-1 text-amber-700 dark:text-amber-300">{totalBeds - occupiedBeds - availableBeds}</p>
                    </div>
                </div>
            </div>

            {/* BED BOARD GRID */}
            <div data-tour="bed-board" className="space-y-6">
                {isLoading ? (
                    <div className="card text-center py-12 text-ink-400"><Activity className="animate-spin mx-auto mb-2" size={20} /> Resolving allocations…</div>
                ) : wards.map(ward => (
                    <div key={ward.id} className="card overflow-hidden">
                        <div className="bg-ink-50/60 dark:bg-ink-800/40 border-b border-ink-100 dark:border-ink-800 p-4 flex justify-between items-center">
                            <h2 className="text-base font-semibold text-ink-900 dark:text-white tracking-tight">{ward.name}</h2>
                            <span className="text-xs font-medium text-ink-500 dark:text-ink-400">Capacity limit: <span className="text-ink-800 dark:text-ink-200 font-semibold">{ward.capacity}</span></span>
                        </div>

                        <div className="p-5 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                            {ward.beds.map(bed => {
                                const variantBg = {
                                    Available: 'bg-white dark:bg-ink-900 border-accent-200 dark:border-accent-500/20 hover:border-accent-400 cursor-pointer hover:-translate-y-0.5',
                                    Occupied:  'bg-blue-50/60 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/20 hover:border-blue-400 cursor-pointer hover:-translate-y-0.5',
                                    Cleaning:  'bg-purple-50 dark:bg-purple-500/10 border-purple-200 dark:border-purple-500/20 hover:border-purple-400 cursor-pointer hover:-translate-y-0.5',
                                }[bed.status] || 'bg-amber-50 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20 hover:border-amber-400 cursor-pointer hover:-translate-y-0.5';
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
                                        onClick={() => bed.status === 'Occupied'
                                            ? setActiveBed({ ...bed, wardName: ward.name })
                                            : setSetupBed({ ...bed, wardName: ward.name })}
                                        className={`relative text-left flex flex-col p-3.5 rounded-xl border transition-all duration-150 ${variantBg}`}>
                                        <span className={`absolute top-3 right-3 size-2 rounded-full ${dotBg}`} />
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
                    <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setIsAdmitModalOpen(false)} />
                    <div className="relative w-full max-w-md bg-white dark:bg-ink-900 h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="p-6 border-b border-ink-100 dark:border-ink-800 bg-gradient-to-br from-brand-600 to-brand-700 text-white shrink-0">
                            <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-brand-200">New admission</span>
                            <h2 className="text-lg font-semibold mt-1 flex items-center gap-2"><UserPlus size={20} className="text-brand-200" /> Admit patient</h2>
                            <p className="text-sm text-brand-100/90 mt-1">Allocate a bed and create a new inpatient admission record.</p>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 sm:p-6 bg-ink-50/40 custom-scrollbar">
                            <form id="admitForm" onSubmit={handleAdmit}>
                                <div className="card p-5 space-y-4">
                                    <div>
                                        <label htmlFor="wards-select-patient" className="label">Select patient</label>
                                        <select id="wards-select-patient" required value={admitForm.patient_id} onChange={(e) => setAdmitForm({...admitForm, patient_id: e.target.value})} className="input">
                                            <option value="">Choose a registered patient…</option>
                                            {patients.map(p => (
                                                <option key={p.patient_id} value={p.patient_id}>
                                                    {p.surname}, {p.other_names} ({p.outpatient_no})
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label htmlFor="wards-select-available-bed" className="label">Select available bed</label>
                                        <select id="wards-select-available-bed" required value={admitForm.bed_id} onChange={(e) => setAdmitForm({...admitForm, bed_id: e.target.value})} className="input">
                                            <option value="">Assign a bed…</option>
                                            {wards.map(ward => (
                                                <optgroup key={ward.id} label={ward.name}>
                                                    {ward.beds.flatMap(bed => bed.status === 'Available' ? [
                                                        <option key={bed.id} value={bed.id}>Bed {bed.number}</option>
                                                    ] : [])}
                                                </optgroup>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label htmlFor="wards-primary-diagnosis-reason-for-admission" className="label">Primary diagnosis (reason for admission)</label>
                                        <input id="wards-primary-diagnosis-reason-for-admission" required type="text" value={admitForm.diagnosis} onChange={(e) => setAdmitForm({...admitForm, diagnosis: e.target.value})} className="input" placeholder="e.g. Severe Malaria" />
                                    </div>
                                </div>
                            </form>
                        </div>

                        <div className="p-5 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex gap-3 shrink-0">
                            <button type="button" onClick={() => setIsAdmitModalOpen(false)} className="btn-secondary">Cancel</button>
                            <button type="submit" form="admitForm" className="btn-primary flex-1">Allocate &amp; admit</button>
                        </div>
                    </div>
                </div>
            )}

            {/* SLIDE-OVER: INPATIENT CHART & AUDIT INVENTORY */}
            {activeBed && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setActiveBed(null)} />
                    <div className="relative w-full max-w-2xl bg-white dark:bg-ink-900 h-full shadow-elevated flex flex-col animate-slide-in-right">

                        <div className="p-6 border-b border-ink-100 dark:border-ink-800 bg-gradient-to-br from-blue-600 to-blue-700 text-white shrink-0">
                            <div className="flex justify-between items-start">
                                <div>
                                    <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-blue-200">Inpatient chart</span>
                                    <h2 className="text-xl font-semibold mt-1 tracking-tight">{activeBed.patient}</h2>
                                    <p className="text-sm text-blue-100/90 mt-1 font-medium">{activeBed.wardName} &middot; Bed {activeBed.number}</p>
                                </div>
                                <button type="button" onClick={() => {setActiveBed(null); setCart([]);}} aria-label="Close" className="text-blue-100 hover:text-white p-2 hover:bg-white/10 rounded-lg"><X size={18}/></button>
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
                                    <input aria-label="Qty" type="number" min="1" placeholder="Qty" value={consumeQty} onChange={(e) => setConsumeQty(e.target.value)} className="input w-20" />
                                    <button type="button" onClick={handleAddToCart} className="btn bg-ink-100 text-ink-800 hover:bg-ink-200">
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
                                                    <th aria-label="Actions"></th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {cart.map(item => (
                                                    <tr key={item.batch_id}>
                                                        <td className="font-medium">{item.name} <span className="text-2xs text-ink-400 block">{item.batch_number}</span></td>
                                                        <td className="font-semibold">{item.qty}</td>
                                                        <td className="text-right">
                                                            <button type="button" onClick={() => setCart(cart.filter(c => c.batch_id !== item.batch_id))} aria-label="Remove" className="text-ink-400 hover:text-rose-600"><Trash2 size={15}/></button>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}

                                <button type="button" onClick={handleConsumeStock} disabled={cart.length === 0 || isConsuming} className="btn-success w-full">
                                    <CheckCircle2 size={16} /> {isConsuming ? 'Processing…' : 'Administer & log to audit trail'}
                                </button>
                            </div>

                            <div className="card-flush p-5">
                                <h3 className="section-eyebrow mb-4 border-b border-ink-100 pb-3">Clinical log</h3>
                                <textarea
                                    rows="3"
                                    aria-label="Clinical log"
                                    value={clinicalNote}
                                    onChange={(e) => setClinicalNote(e.target.value)}
                                    className="input resize-none mb-3"
                                    placeholder="Append observation parameters… (e.g. vitals, medication response, mood)"
                                />
                                <button type="button" onClick={handleSaveClinicalNote} disabled={isSavingNote || !clinicalNote.trim()} className="btn bg-ink-800 text-white hover:bg-ink-900 w-full disabled:opacity-50 disabled:cursor-not-allowed">
                                    {isSavingNote ? 'Saving…' : 'Commit observation'}
                                </button>
                            </div>
                        </div>

                        <div className="p-5 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 shrink-0 space-y-2">
                            <button type="button"
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
                            <button type="button" onClick={handleDischarge} className="btn-danger w-full bg-rose-50 text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100 shadow-none">
                                <LogOut size={16} /> Execute discharge protocol
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {isSetupOpen && (
                <WardSetupModal
                    wards={wards}
                    onClose={() => setIsSetupOpen(false)}
                    onSaved={() => { setIsSetupOpen(false); fetchBedBoard(); }}
                />
            )}

            {setupBed && (
                <BedActionModal
                    bed={setupBed}
                    onClose={() => setSetupBed(null)}
                    onSaved={() => { setSetupBed(null); fetchBedBoard(); }}
                />
            )}
        </div>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Ward & bed setup modal.                                                   */
/*                                                                            */
/*  Two tabs: create a new ward (name + capacity) or add beds to an existing  */
/*  ward — a single named bed, or a bulk run auto-numbered after a prefix.    */
/*  Beds land "Available" so they're immediately allocatable from /admit.     */
/* ────────────────────────────────────────────────────────────────────────── */
function WardSetupModal({ wards, onClose, onSaved }) {
    const [tab, setTab] = useState(wards.length === 0 ? 'ward' : 'beds');
    const [saving, setSaving] = useState(false);
    const [wardForm, setWardForm] = useState({ name: '', capacity: '' });
    const [bedForm, setBedForm] = useState({
        ward_id: wards[0]?.id ? String(wards[0].id) : '',
        mode: 'bulk', bed_number: '', count: '', prefix: '',
    });

    const submitWard = async () => {
        const capacity = parseInt(wardForm.capacity, 10);
        if (!wardForm.name.trim() || !Number.isFinite(capacity) || capacity < 1) {
            toast.error('Enter a ward name and a capacity of at least 1.');
            return;
        }
        setSaving(true);
        try {
            await apiClient.post('/wards/', { name: wardForm.name.trim(), capacity });
            toast.success(`Ward "${wardForm.name.trim()}" created — now add its beds.`);
            onSaved();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Could not create ward.');
        } finally {
            setSaving(false);
        }
    };

    const submitBeds = async () => {
        if (!bedForm.ward_id) { toast.error('Pick a ward first.'); return; }
        const payload = bedForm.mode === 'single'
            ? { bed_number: bedForm.bed_number.trim() }
            : { count: parseInt(bedForm.count, 10), prefix: bedForm.prefix.trim() || undefined };
        if (bedForm.mode === 'single' && !payload.bed_number) {
            toast.error('Enter a bed number.'); return;
        }
        if (bedForm.mode === 'bulk' && (!Number.isFinite(payload.count) || payload.count < 1)) {
            toast.error('Enter how many beds to add.'); return;
        }
        setSaving(true);
        try {
            const r = await apiClient.post(`/wards/${bedForm.ward_id}/beds`, payload);
            toast.success(r.data?.message || 'Beds added.');
            onSaved();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Could not add beds.');
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4" role="dialog" aria-modal="true">
            <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative bg-white dark:bg-ink-900 rounded-2xl shadow-elevated w-full max-w-md overflow-hidden flex flex-col">
                <div className="flex items-center justify-between p-5 border-b border-ink-100 dark:border-ink-800 shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="size-9 rounded-xl bg-gradient-to-br from-brand-500 to-teal-500 text-white flex items-center justify-center shadow-soft">
                            <Bed size={17} />
                        </div>
                        <div>
                            <h3 className="text-base font-semibold text-ink-900 dark:text-white tracking-tight">Set up wards &amp; beds</h3>
                            <p className="text-xs text-ink-500 dark:text-ink-400">Beds must exist here before they can be allocated.</p>
                        </div>
                    </div>
                    <button type="button" onClick={onClose} aria-label="Close" className="text-ink-400 hover:text-ink-700 dark:hover:text-ink-200 p-2 hover:bg-ink-100 dark:hover:bg-ink-800/50 rounded-full">
                        <X size={18} />
                    </button>
                </div>

                <div className="px-5 pt-4 flex gap-2">
                    <button type="button" onClick={() => setTab('ward')}
                        className={tab === 'ward' ? 'btn-primary text-xs py-1.5' : 'btn-secondary text-xs py-1.5'}>
                        New ward
                    </button>
                    <button type="button" onClick={() => setTab('beds')} disabled={wards.length === 0}
                        className={tab === 'beds' ? 'btn-primary text-xs py-1.5' : 'btn-secondary text-xs py-1.5'}>
                        Add beds
                    </button>
                </div>

                {tab === 'ward' ? (
                    <div className="p-5 space-y-3">
                        <div>
                            <label htmlFor="ward-setup-name" className="label">Ward name</label>
                            <input id="ward-setup-name" type="text" className="input" value={wardForm.name}
                                onChange={(e) => setWardForm({ ...wardForm, name: e.target.value })}
                                placeholder="e.g. Maternity Wing" />
                        </div>
                        <div>
                            <label htmlFor="ward-setup-capacity" className="label">Bed capacity</label>
                            <input id="ward-setup-capacity" type="number" min="1" className="input" value={wardForm.capacity}
                                onChange={(e) => setWardForm({ ...wardForm, capacity: e.target.value })}
                                placeholder="e.g. 12" />
                            <p className="text-2xs text-ink-500 dark:text-ink-400 mt-1">The maximum number of beds this ward can hold.</p>
                        </div>
                    </div>
                ) : (
                    <div className="p-5 space-y-3">
                        <div>
                            <label htmlFor="bed-setup-ward" className="label">Ward</label>
                            <select id="bed-setup-ward" className="input" value={bedForm.ward_id}
                                onChange={(e) => setBedForm({ ...bedForm, ward_id: e.target.value })}>
                                {wards.map((w) => (
                                    <option key={w.id} value={w.id}>{w.name} ({w.beds.length}/{w.capacity} beds)</option>
                                ))}
                            </select>
                        </div>
                        <fieldset>
                            <legend className="label">How many?</legend>
                            <div className="flex gap-2">
                                <button type="button" onClick={() => setBedForm({ ...bedForm, mode: 'bulk' })}
                                    className={bedForm.mode === 'bulk' ? 'btn-primary text-xs py-1.5 flex-1' : 'btn-secondary text-xs py-1.5 flex-1'}>
                                    Several at once
                                </button>
                                <button type="button" onClick={() => setBedForm({ ...bedForm, mode: 'single' })}
                                    className={bedForm.mode === 'single' ? 'btn-primary text-xs py-1.5 flex-1' : 'btn-secondary text-xs py-1.5 flex-1'}>
                                    One named bed
                                </button>
                            </div>
                        </fieldset>
                        {bedForm.mode === 'single' ? (
                            <div>
                                <label htmlFor="bed-setup-number" className="label">Bed number</label>
                                <input id="bed-setup-number" type="text" className="input" value={bedForm.bed_number}
                                    onChange={(e) => setBedForm({ ...bedForm, bed_number: e.target.value })}
                                    placeholder="e.g. MAT-1" />
                            </div>
                        ) : (
                            <div className="grid grid-cols-2 gap-3">
                                <div>
                                    <label htmlFor="bed-setup-count" className="label">Number of beds</label>
                                    <input id="bed-setup-count" type="number" min="1" max="200" className="input" value={bedForm.count}
                                        onChange={(e) => setBedForm({ ...bedForm, count: e.target.value })}
                                        placeholder="e.g. 10" />
                                </div>
                                <div>
                                    <label htmlFor="bed-setup-prefix" className="label">Numbering prefix</label>
                                    <input id="bed-setup-prefix" type="text" className="input" value={bedForm.prefix}
                                        onChange={(e) => setBedForm({ ...bedForm, prefix: e.target.value })}
                                        placeholder="auto (ward initials)" />
                                </div>
                            </div>
                        )}
                    </div>
                )}

                <div className="p-4 border-t border-ink-100 dark:border-ink-800 flex justify-end gap-2 bg-ink-50/40 dark:bg-ink-800/40">
                    <button type="button" onClick={onClose} className="btn-secondary cursor-pointer">Cancel</button>
                    <button type="button" onClick={tab === 'ward' ? submitWard : submitBeds} disabled={saving} className="btn-primary cursor-pointer">
                        {saving
                            ? <><Activity size={14} className="animate-spin" /> Saving…</>
                            : <><Plus size={14} /> {tab === 'ward' ? 'Create ward' : 'Add beds'}</>}
                    </button>
                </div>
            </div>
        </div>
    );
}

/* ────────────────────────────────────────────────────────────────────────── */
/*  Bed action sheet — status changes for non-occupied beds.                  */
/*                                                                            */
/*  This is also the housekeeping loop: discharge flags a bed "Cleaning" and  */
/*  this sheet is how it returns to "Available" for the next allocation.      */
/* ────────────────────────────────────────────────────────────────────────── */
function BedActionModal({ bed, onClose, onSaved }) {
    const [busy, setBusy] = useState(false);

    const setStatus = async (status) => {
        setBusy(true);
        try {
            await apiClient.patch(`/wards/beds/${bed.id}`, { status });
            toast.success(`Bed ${bed.number} marked ${status}.`);
            onSaved();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Could not update bed.');
        } finally {
            setBusy(false);
        }
    };

    const deleteBed = async () => {
        if (!window.confirm(`Delete bed ${bed.number} from ${bed.wardName}? This cannot be undone.`)) return;
        setBusy(true);
        try {
            await apiClient.delete(`/wards/beds/${bed.id}`);
            toast.success(`Bed ${bed.number} deleted.`);
            onSaved();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Could not delete bed.');
        } finally {
            setBusy(false);
        }
    };

    const statuses = ['Available', 'Cleaning', 'Maintenance'].filter((s) => s !== bed.status);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4" role="dialog" aria-modal="true">
            <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={onClose} />
            <div className="relative bg-white dark:bg-ink-900 rounded-2xl shadow-elevated w-full max-w-xs overflow-hidden">
                <div className="flex items-center justify-between p-4 border-b border-ink-100 dark:border-ink-800">
                    <div>
                        <h3 className="text-sm font-semibold text-ink-900 dark:text-white">Bed {bed.number}</h3>
                        <p className="text-xs text-ink-500 dark:text-ink-400">{bed.wardName} · currently {bed.status}</p>
                    </div>
                    <button type="button" onClick={onClose} aria-label="Close" className="text-ink-400 hover:text-ink-700 dark:hover:text-ink-200 p-2 hover:bg-ink-100 dark:hover:bg-ink-800/50 rounded-full">
                        <X size={16} />
                    </button>
                </div>
                <div className="p-4 space-y-2">
                    {statuses.map((s) => (
                        <button key={s} type="button" disabled={busy} onClick={() => setStatus(s)} className="btn-secondary w-full justify-center text-sm">
                            {s === 'Available' ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />} Mark {s}
                        </button>
                    ))}
                    <button type="button" disabled={busy} onClick={deleteBed} className="btn-danger w-full justify-center text-sm bg-rose-50 text-rose-700 ring-1 ring-rose-200 hover:bg-rose-100 shadow-none">
                        <Trash2 size={14} /> Delete bed
                    </button>
                </div>
            </div>
        </div>
    );
}