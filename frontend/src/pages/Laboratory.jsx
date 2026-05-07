import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
    Microscope, Search, Clock, AlertCircle, CheckCircle2,
    Printer, XCircle, TestTube, FileDigit, ChevronDown, ChevronUp,
    Settings, Activity, FlaskConical, Send, Package, Plus, Trash2
} from 'lucide-react';
import toast from 'react-hot-toast';
import { printLabReport } from '../utils/printTemplates';

export default function Laboratory() {
    const [activeTab, setActiveTab] = useState('queue');
    const [isQueueOpen, setIsQueueOpen] = useState(true);
    const [isLoading, setIsLoading] = useState(true);

    // --- DYNAMIC SYSTEM STATE ---
    const [catalog, setCatalog] = useState([]);
    const [queue, setQueue] = useState([]);
    const [labInventory, setLabInventory] = useState([]);

    // --- WORKSPACE STATE ---
    const [activeTest, setActiveTest] = useState(null);
    const [results, setResults] = useState({});
    const [techNotes, setTechNotes] = useState('');
    
    // Inventory tracking state for the current test
    const [consumedItems, setConsumedItems] = useState([]);
    const [selectedBatchId, setSelectedBatchId] = useState('');
    const [consumeQty, setConsumeQty] = useState('');

    // --- DATA FETCHING ---
    useEffect(() => {
        fetchLaboratoryData();
    }, []);

    const fetchLaboratoryData = async () => {
        setIsLoading(true);
        try {
            // Fetch the 3 critical data streams for the Lab
            const [queueRes, invRes, catRes] = await Promise.all([
                apiClient.get('/laboratory/queue').catch(() => ({ data: [] })),
                apiClient.get('/laboratory/inventory').catch(() => ({ data: [] })),
                apiClient.get('/laboratory/catalog').catch(() => ({ data: [] }))
            ]);
            
            setQueue(queueRes.data || []);
            setLabInventory(invRes.data || []);
            setCatalog(catRes.data || []);
        } catch (error) {
            toast.error("Failed to sync Laboratory Data.");
        } finally {
            setIsLoading(false);
        }
    };

    const handleTestSelect = (test) => {
        setActiveTest(test);
        setIsQueueOpen(false);
        setResults({});
        setTechNotes('');
        setConsumedItems([]); // Reset cart for new test
    };

    const handleAcknowledgeSpecimen = () => {
        toast.success("Barcode generated. Specimen received.");
        setActiveTest({ ...activeTest, status: 'In Progress' });
        setQueue(queue.map(q => q.test_id === activeTest.test_id ? { ...q, status: 'In Progress' } : q));
    };

    // --- INVENTORY HANDLERS ---
    const addConsumedItem = () => {
        if (!selectedBatchId || !consumeQty || consumeQty <= 0) return;
        
        const inventoryItem = labInventory.find(i => i.batch_id === parseInt(selectedBatchId));
        if (!inventoryItem) return;

        if (parseInt(consumeQty) > inventoryItem.stock) {
            return toast.error(`Only ${inventoryItem.stock} available in this batch.`);
        }

        const existing = consumedItems.find(c => c.batch_id === inventoryItem.batch_id);
        if (existing) {
            setConsumedItems(consumedItems.map(c => c.batch_id === inventoryItem.batch_id ? { ...c, quantity: c.quantity + parseInt(consumeQty) } : c));
        } else {
            setConsumedItems([...consumedItems, { ...inventoryItem, quantity: parseInt(consumeQty) }]);
        }
        
        setSelectedBatchId('');
        setConsumeQty('');
    };

    const removeConsumedItem = (batch_id) => {
        setConsumedItems(consumedItems.filter(c => c.batch_id !== batch_id));
    };

    const handleRejectSample = async () => {
        if (!activeTest) return;
        const reason = window.prompt(
            'Reason for rejecting this sample (e.g. haemolysis, wrong specimen, insufficient volume):'
        );
        if (!reason) return;
        try {
            await apiClient.post(`/laboratory/tests/${activeTest.test_id}/reject`, { reason });
            toast.success('Sample rejected. Requesting clinician will be notified.');
            setQueue(queue.filter(q => q.test_id !== activeTest.test_id));
            setActiveTest(null);
            setIsQueueOpen(true);
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Reject failed.');
        }
    };

    const handleReleaseResults = async () => {
        const payload = {
            result_data: results,
            tech_notes: techNotes,
            consumed_items: consumedItems.map(c => ({ batch_id: c.batch_id, quantity: c.quantity }))
        };

        try {
            await apiClient.post(`/laboratory/tests/${activeTest.test_id}/complete`, payload);
            toast.success("Results Verified & Inventory Deducted Automatically.");
            
            setQueue(queue.filter(q => q.test_id !== activeTest.test_id));
            setActiveTest(null);
            setIsQueueOpen(true);
            fetchLaboratoryData(); // Refresh data to show inventory deductions
        } catch (error) {
            toast.error(error.response?.data?.detail || "Failed to commit results.");
        }
    };

    const getFlag = (val, min, max) => {
        if (!val) return null;
        const num = parseFloat(val);
        if (num < min) return <span className="badge-info">Low</span>;
        if (num > max) return <span className="badge-danger">High</span>;
        return <span className="badge-success">Normal</span>;
    };

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">

            {/* LIS HEADER & TABS */}
            <div className="card p-2 flex items-center justify-between shrink-0">
                <div role="tablist" aria-label="Laboratory mode" className="flex bg-ink-100/70 p-1 rounded-xl w-full max-w-md">
                    <button role="tab" aria-selected={activeTab === 'queue'} onClick={() => setActiveTab('queue')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium transition-all ${activeTab === 'queue' ? 'bg-white text-ink-900 shadow-soft ring-1 ring-ink-200/70' : 'text-ink-600 hover:text-ink-900'}`}>
                        <Microscope size={16} className={activeTab === 'queue' ? 'text-brand-600' : 'text-ink-400'} /> Lab Operations
                    </button>
                    <button role="tab" aria-selected={activeTab === 'catalog'} onClick={() => setActiveTab('catalog')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium transition-all ${activeTab === 'catalog' ? 'bg-white text-ink-900 shadow-soft ring-1 ring-ink-200/70' : 'text-ink-600 hover:text-ink-900'}`}>
                        <FileDigit size={16} className={activeTab === 'catalog' ? 'text-accent-600' : 'text-ink-400'} /> Test Catalog
                    </button>
                </div>
            </div>

            {/* ========================================= */}
            {/* MODE 1: LAB OPERATIONS (RESULTING QUEUE)  */}
            {/* ========================================= */}
            {activeTab === 'queue' && (
                <>
                    {/* COLLAPSIBLE QUEUE */}
                    <div className="card shrink-0 flex flex-col z-20">
                        <button onClick={() => setIsQueueOpen(!isQueueOpen)} className="w-full p-4 flex justify-between items-center bg-ink-50/60 hover:bg-brand-50/40 transition-colors rounded-t-2xl focus:outline-none">
                            <div className="flex items-center gap-3">
                                <TestTube className="text-brand-600" size={18} />
                                <h2 className="font-semibold text-ink-900 text-base tracking-tight">Pending lab orders</h2>
                                <span className="badge-brand">{queue.length} Tests</span>
                            </div>
                            <span className="text-ink-500">{isQueueOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</span>
                        </button>

                        {isQueueOpen && (
                            <div className="border-t border-ink-100 p-4 bg-white rounded-b-2xl">
                                {isLoading ? (
                                    <div className="text-center py-6 text-ink-400"><Activity className="animate-spin mx-auto mb-2 text-brand-500" size={20} /> Syncing orders&hellip;</div>
                                ) : queue.length === 0 ? (
                                    <div className="text-center py-6 text-ink-400">No pending lab tests in queue.</div>
                                ) : (
                                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                        {queue.map((order) => {
                                            const active = activeTest?.test_id === order.test_id;
                                            return (
                                                <button key={order.test_id} type="button" onClick={() => handleTestSelect(order)} className={`text-left p-3 rounded-xl border transition-all duration-150 ${active ? 'bg-brand-50/60 border-brand-400 ring-2 ring-brand-500/15' : 'bg-white border-ink-200 hover:border-brand-300 hover:-translate-y-0.5'}`}>
                                                    <div className="flex justify-between items-start mb-2">
                                                        <h3 className="font-semibold text-sm text-ink-900 line-clamp-1">{order.test_name}</h3>
                                                        {order.priority === 'STAT' && <AlertCircle size={14} className="text-rose-500 animate-pulse-soft shrink-0" />}
                                                    </div>
                                                    <div className="flex justify-between items-center text-xs text-ink-500 mb-2">
                                                        <span className="font-medium text-ink-800">{order.patient}</span>
                                                        <span className="font-mono text-2xs text-ink-400">#{order.test_id}</span>
                                                    </div>
                                                    <div className="flex justify-between items-center text-xs">
                                                        <span className={order.status === 'Pending Collection' ? 'badge-warn' : 'badge-info'}>{order.status}</span>
                                                        <span className="text-ink-400 flex items-center gap-1"><Clock size={10} /> {new Date(order.requested_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                                                    </div>
                                                </button>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* LAB WORKSPACE */}
                    <div className="flex-1 card overflow-hidden flex flex-col z-10 relative">
                        {!activeTest ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-ink-400 bg-ink-50/40">
                                <FlaskConical size={56} className="mb-4 text-ink-300" strokeWidth={1.5} />
                                <h3 className="text-base font-semibold text-ink-600 mb-1">Laboratory workbench</h3>
                                <p className="text-sm">Select a pending test from the queue to process specimens and enter results.</p>
                            </div>
                        ) : (
                            <>
                                {/* Workbench Header */}
                                <div className="shrink-0 p-5 border-b border-ink-100 bg-white flex justify-between items-center z-10">
                                    <div className="flex gap-4 items-center flex-1 min-w-0">
                                        <div className="w-11 h-11 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center ring-1 ring-inset ring-brand-100">
                                            <Microscope size={20} />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2 mb-1">
                                                <h1 className="text-lg font-semibold text-ink-900 tracking-tight truncate">{activeTest.test_name}</h1>
                                                {activeTest.priority === 'STAT' && <span className="badge-danger animate-pulse-soft">STAT</span>}
                                            </div>
                                            <p className="text-xs font-medium text-ink-500 truncate">
                                                Patient: <span className="text-ink-700">{activeTest.patient}</span> &middot; Ordered by: <span className="text-ink-700">{activeTest.doctor}</span> &middot; #{activeTest.test_id}
                                            </p>
                                        </div>
                                        {(activeTest.status === 'Completed' || activeTest.result_summary) && (
                                            <button
                                                onClick={() => printLabReport({
                                                    patient: { full_name: activeTest.patient, outpatient_no: activeTest.op_no },
                                                    test: activeTest,
                                                    performedBy: { full_name: activeTest.performed_by_name },
                                                    orderedBy: { full_name: activeTest.doctor },
                                                })}
                                                className="btn-secondary shrink-0"
                                                title="Print lab report"
                                            >
                                                <Printer size={15} /> Print report
                                            </button>
                                        )}
                                    </div>
                                </div>

                                {/* Scrolling Workspace Body */}
                                <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-5 bg-ink-50/40 custom-scrollbar">

                                    {activeTest.status === 'Pending Collection' ? (
                                        <div className="card p-6 text-center py-12">
                                            <TestTube size={44} className="mx-auto text-ink-300 mb-4" />
                                            <h3 className="text-base font-semibold text-ink-800 mb-1">Awaiting specimen collection</h3>
                                            <p className="text-sm text-ink-500 mb-6 max-w-md mx-auto">Please collect the required specimen from the patient. Generate a barcode label to track the sample through the analyzers.</p>
                                            <div className="flex flex-wrap justify-center gap-3">
                                                <button onClick={() => { setActiveTest(null); setIsQueueOpen(true); }} className="btn-secondary text-rose-600 border-rose-200 hover:bg-rose-50">
                                                    <XCircle size={16} /> Reject / no-show
                                                </button>
                                                <button onClick={handleAcknowledgeSpecimen} className="btn-primary">
                                                    <Printer size={16} /> Print barcode & receive specimen
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <>
                                            <div className="card-flush p-5 sm:p-6 animate-fade-in">
                                                <h3 className="section-eyebrow mb-5 border-b border-ink-100 pb-3 flex items-center gap-2">
                                                    <Activity className="text-brand-600" size={16} /> Enter discrete results
                                                </h3>

                                                {activeTest.test_name.includes('CBC') || activeTest.test_name.includes('Blood') ? (
                                                    <div className="space-y-3 overflow-x-auto pb-2">
                                                        <div className="grid grid-cols-12 gap-3 items-center bg-ink-50 p-3 rounded-xl ring-1 ring-ink-100 text-2xs font-semibold text-ink-500 uppercase tracking-wider min-w-[600px]">
                                                            <div className="col-span-4">Parameter</div>
                                                            <div className="col-span-3">Result value</div>
                                                            <div className="col-span-2">Unit</div>
                                                            <div className="col-span-2">Ref. range</div>
                                                            <div className="col-span-1 text-center">Flag</div>
                                                        </div>

                                                        {[
                                                            { key: 'wbc', name: 'White Blood Cells (WBC)', unit: 'x10⁹/L', min: 4.0, max: 11.0 },
                                                            { key: 'hgb', name: 'Hemoglobin (HGB)',         unit: 'g/dL',   min: 12.0, max: 16.0 },
                                                        ].map(param => (
                                                            <div key={param.key} className="grid grid-cols-12 gap-3 items-center border-b border-ink-100 pb-2 min-w-[600px]">
                                                                <div className="col-span-4 font-medium text-sm text-ink-700">{param.name}</div>
                                                                <div className="col-span-3">
                                                                    <input
                                                                        type="number" step="0.1"
                                                                        value={results[param.key] || ''}
                                                                        onChange={(e) => setResults({...results, [param.key]: e.target.value})}
                                                                        className="input"
                                                                    />
                                                                </div>
                                                                <div className="col-span-2 text-sm text-ink-500">{param.unit}</div>
                                                                <div className="col-span-2 text-xs font-mono text-ink-400">{param.min} – {param.max}</div>
                                                                <div className="col-span-1 flex justify-center">
                                                                    {getFlag(results[param.key], param.min, param.max)}
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <div>
                                                        <label className="label">Qualitative result / impression</label>
                                                        <textarea
                                                            rows="3"
                                                            value={results.qualitative || ''}
                                                            onChange={(e) => setResults({ qualitative: e.target.value })}
                                                            className="input resize-none"
                                                            placeholder="Enter qualitative findings…"
                                                        />
                                                    </div>
                                                )}

                                                <div className="mt-4">
                                                    <label className="label">Technician notes (optional)</label>
                                                    <input type="text" value={techNotes} onChange={(e) => setTechNotes(e.target.value)} className="input" placeholder="Methodology notes…" />
                                                </div>
                                            </div>

                                            <div className="card-flush p-5 sm:p-6 border-l-4 border-l-amber-400">
                                                <h3 className="section-eyebrow mb-4 border-b border-ink-100 pb-3 flex items-center gap-2">
                                                    <Package className="text-amber-500" size={16} /> Reagents &amp; consumables used
                                                </h3>

                                                <div className="flex flex-wrap gap-2 mb-4">
                                                    <select value={selectedBatchId} onChange={(e) => setSelectedBatchId(e.target.value)} className="input flex-1 min-w-[12rem]">
                                                        <option value="">Select item from lab store…</option>
                                                        {labInventory.map(item => (
                                                            <option key={item.batch_id} value={item.batch_id}>
                                                                {item.name} (Batch {item.batch_no}) – {item.stock} {item.unit} avail.
                                                            </option>
                                                        ))}
                                                    </select>
                                                    <input type="number" min="1" placeholder="Qty" value={consumeQty} onChange={(e) => setConsumeQty(e.target.value)} className="input w-24" />
                                                    <button onClick={addConsumedItem} className="btn bg-ink-800 text-white hover:bg-ink-900">
                                                        <Plus size={15} /> Add
                                                    </button>
                                                </div>

                                                {consumedItems.length > 0 && (
                                                    <div className="card-flush overflow-x-auto">
                                                        <table className="table-clean min-w-[400px]">
                                                            <thead>
                                                                <tr>
                                                                    <th>Item &amp; batch</th>
                                                                    <th>Qty used</th>
                                                                    <th></th>
                                                                </tr>
                                                            </thead>
                                                            <tbody>
                                                                {consumedItems.map(item => (
                                                                    <tr key={item.batch_id}>
                                                                        <td className="font-medium text-ink-900">{item.name} <span className="text-xs text-ink-500">({item.batch_no})</span></td>
                                                                        <td className="font-semibold">{item.quantity} {item.unit}</td>
                                                                        <td className="text-right">
                                                                            <button onClick={() => removeConsumedItem(item.batch_id)} aria-label="Remove" className="text-ink-400 hover:text-rose-600"><Trash2 size={15} /></button>
                                                                        </td>
                                                                    </tr>
                                                                ))}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                )}
                                                {consumedItems.length === 0 && <p className="text-xs text-ink-400 italic">No consumables logged. Reagents must be logged to maintain accurate stock levels.</p>}
                                            </div>
                                        </>
                                    )}
                                </div>

                                {/* Workbench Footer Actions */}
                                {activeTest.status === 'In Progress' && (
                                    <div className="p-4 border-t border-ink-100 bg-white flex justify-end gap-2 shrink-0 z-10">
                                        <button onClick={handleRejectSample} className="btn-secondary text-rose-600 border-rose-200 hover:bg-rose-50">
                                            <XCircle size={16} /> Reject sample
                                        </button>
                                        <button onClick={handleReleaseResults} className="btn-success">
                                            <Send size={16} /> Verify, release &amp; deduct stock
                                        </button>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </>
            )}

            {/* ========================================= */}
            {/* MODE 2: ADMIN TEST CATALOG (READ-ONLY)    */}
            {/* ========================================= */}
            {activeTab === 'catalog' && (
                <div className="flex-1 card flex flex-col overflow-hidden">
                    <div className="p-5 border-b border-ink-100 bg-ink-50/40 flex justify-between items-center">
                        <div>
                            <span className="section-eyebrow">Admin</span>
                            <h2 className="text-base font-semibold text-ink-900 mt-1 flex items-center gap-2 tracking-tight">
                                <Settings className="text-ink-400" size={18} /> Managed test directory
                            </h2>
                            <p className="text-sm text-ink-500 mt-1">This catalog is managed by hospital administration and determines what doctors can order.</p>
                        </div>
                    </div>

                    <div className="flex-1 overflow-auto">
                        <table className="table-clean min-w-[500px]">
                            <thead>
                                <tr>
                                    <th>Test code &amp; name</th>
                                    <th>Category</th>
                                    <th>Description / specimen</th>
                                </tr>
                            </thead>
                            <tbody>
                                {isLoading ? (
                                    <tr><td colSpan="3" className="text-center py-8 text-ink-400">Loading catalog…</td></tr>
                                ) : catalog.length === 0 ? (
                                    <tr><td colSpan="3" className="text-center py-8 text-ink-500">No laboratory packages found in admin pricing catalog.</td></tr>
                                ) : catalog.map((test) => (
                                    <tr key={test.catalog_id}>
                                        <td>
                                            <div className="font-semibold text-ink-900">{test.test_name}</div>
                                            <div className="text-xs font-mono text-ink-500 mt-0.5">PKG-LAB-{String(test.catalog_id).padStart(4, '0')}</div>
                                        </td>
                                        <td className="font-medium text-ink-700">{test.category}</td>
                                        <td>
                                            <span className="badge-neutral">{test.default_specimen_type || 'General'}</span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}