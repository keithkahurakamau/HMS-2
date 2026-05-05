import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { 
    Microscope, Search, Clock, AlertCircle, CheckCircle2, 
    Printer, XCircle, TestTube, FileDigit, ChevronDown, ChevronUp,
    Settings, Activity, FlaskConical, Send, Package, Plus, Trash2
} from 'lucide-react';
import toast from 'react-hot-toast';

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
        if (num < min) return <span className="text-xs font-bold text-blue-600 bg-blue-50 px-2 py-1 rounded">LOW</span>;
        if (num > max) return <span className="text-xs font-bold text-red-600 bg-red-50 px-2 py-1 rounded">HIGH</span>;
        return <span className="text-xs font-bold text-green-600 bg-green-50 px-2 py-1 rounded">NORMAL</span>;
    };

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">
            
            {/* LIS HEADER & TABS */}
            <div className="bg-white border border-slate-200 rounded-xl p-2 shadow-sm flex items-center justify-between shrink-0">
                <div className="flex bg-slate-100 p-1 rounded-lg w-full max-w-md">
                    <button onClick={() => setActiveTab('queue')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-md text-sm font-bold transition-all ${activeTab === 'queue' ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                        <Microscope size={18} /> Lab Operations
                    </button>
                    <button onClick={() => setActiveTab('catalog')} className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-md text-sm font-bold transition-all ${activeTab === 'catalog' ? 'bg-white text-accent-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}>
                        <FileDigit size={18} /> Test Catalog (Admin)
                    </button>
                </div>
            </div>

            {/* ========================================= */}
            {/* MODE 1: LAB OPERATIONS (RESULTING QUEUE)  */}
            {/* ========================================= */}
            {activeTab === 'queue' && (
                <>
                    {/* COLLAPSIBLE QUEUE */}
                    <div className="bg-white border border-slate-200 rounded-xl shadow-sm shrink-0 flex flex-col z-30">
                        <button onClick={() => setIsQueueOpen(!isQueueOpen)} className="w-full p-4 flex justify-between items-center bg-slate-50 hover:bg-brand-50 transition-colors rounded-t-xl focus:outline-none">
                            <div className="flex items-center gap-3">
                                <TestTube className="text-brand-600" size={20} />
                                <h2 className="font-bold text-slate-800 text-lg">Pending Lab Orders</h2>
                                <span className="bg-brand-100 text-brand-700 text-xs font-bold px-2.5 py-1 rounded-full">{queue.length} Tests</span>
                            </div>
                            <div className="flex items-center gap-2 text-slate-500 text-sm font-medium">
                                {isQueueOpen ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                            </div>
                        </button>

                        {isQueueOpen && (
                            <div className="border-t border-slate-100 p-4 bg-white rounded-b-xl">
                                {isLoading ? (
                                    <div className="text-center py-6 text-slate-400"><Activity className="animate-spin mx-auto mb-2 text-brand-500" /> Syncing Orders...</div>
                                ) : queue.length === 0 ? (
                                    <div className="text-center py-6 text-slate-400">No pending lab tests in queue.</div>
                                ) : (
                                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                        {queue.map((order) => (
                                            <div key={order.test_id} onClick={() => handleTestSelect(order)} className={`p-3 rounded-lg border cursor-pointer transition-all ${activeTest?.test_id === order.test_id ? 'bg-brand-50 border-brand-500 shadow-sm ring-1 ring-brand-500' : 'bg-white hover:border-brand-300'}`}>
                                                <div className="flex justify-between items-start mb-2">
                                                    <h3 className="font-bold text-sm text-slate-900 line-clamp-1">{order.test_name}</h3>
                                                    {order.priority === 'STAT' && <AlertCircle size={14} className="text-red-500 animate-pulse shrink-0" />}
                                                </div>
                                                <div className="flex justify-between items-center text-xs text-slate-500 mb-2">
                                                    <span className="font-semibold text-slate-700">{order.patient}</span>
                                                    <span className="font-mono text-slate-400">ID: {order.test_id}</span>
                                                </div>
                                                <div className="flex justify-between items-center text-xs">
                                                    <span className={`px-2 py-0.5 rounded font-bold ${order.status === 'Pending Collection' ? 'bg-orange-50 text-orange-600' : 'bg-blue-50 text-blue-600'}`}>{order.status}</span>
                                                    <span className="text-slate-400 flex items-center gap-1"><Clock size={10} /> {new Date(order.requested_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* LAB WORKSPACE */}
                    <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col z-10 relative">
                        {!activeTest ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-slate-400 bg-slate-50/50">
                                <FlaskConical size={64} className="mb-4 text-slate-300" strokeWidth={1.5} />
                                <h3 className="text-lg font-semibold text-slate-600 mb-1">Laboratory Workbench</h3>
                                <p className="text-sm">Select a pending test from the queue to process specimens and enter results.</p>
                            </div>
                        ) : (
                            <>
                                {/* Workbench Header */}
                                <div className="shrink-0 p-5 border-b border-slate-200 bg-white flex justify-between items-center shadow-[0_2px_4px_rgba(0,0,0,0.02)] z-10">
                                    <div className="flex gap-4 items-center">
                                        <div className="w-12 h-12 bg-brand-50 text-brand-600 rounded-lg flex items-center justify-center border border-brand-100">
                                            <Microscope size={24} />
                                        </div>
                                        <div>
                                            <div className="flex items-center gap-2 mb-1">
                                                <h1 className="text-xl font-bold text-slate-900">{activeTest.test_name}</h1>
                                                {activeTest.priority === 'STAT' && <span className="bg-red-100 text-red-700 text-[10px] font-black px-2 py-0.5 rounded uppercase tracking-wider">STAT / Urgent</span>}
                                            </div>
                                            <p className="text-sm font-medium text-slate-500">
                                                Patient: <span className="text-slate-700">{activeTest.patient}</span> • Ordered by: <span className="text-slate-700">{activeTest.doctor}</span> • Order ID: {activeTest.test_id}
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                {/* Scrolling Workspace Body */}
                                <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50/50">
                                    
                                    {activeTest.status === 'Pending Collection' ? (
                                        <div className="bg-white border border-slate-200 p-6 rounded-xl shadow-sm text-center py-12">
                                            <TestTube size={48} className="mx-auto text-slate-300 mb-4" />
                                            <h3 className="text-lg font-bold text-slate-800 mb-2">Awaiting Specimen Collection</h3>
                                            <p className="text-sm text-slate-500 mb-6 max-w-md mx-auto">Please collect the required specimen from the patient. Generate a barcode label to track the sample through the analyzers.</p>
                                            <div className="flex justify-center gap-4">
                                                <button onClick={() => { setActiveTest(null); setIsQueueOpen(true); }} className="px-6 py-2.5 border border-red-200 text-red-600 hover:bg-red-50 rounded-lg text-sm font-bold flex items-center gap-2">
                                                    <XCircle size={18} /> Reject / No Show
                                                </button>
                                                <button onClick={handleAcknowledgeSpecimen} className="px-6 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-bold flex items-center gap-2 shadow-sm">
                                                    <Printer size={18} /> Print Barcode & Receive Specimen
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <>
                                            {/* STEP 1: Discrete Data Resulting */}
                                            <div className="bg-white border border-slate-200 p-6 rounded-xl shadow-sm animate-in fade-in slide-in-from-bottom-4">
                                                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-6 flex items-center gap-2 border-b border-slate-100 pb-3">
                                                    <Activity className="text-brand-600" size={18} /> Enter Discrete Results
                                                </h3>

                                                {/* Fallback to simple qualitative input if not a specialized discrete test */}
                                                {activeTest.test_name.includes('CBC') || activeTest.test_name.includes('Blood') ? (
                                                    <div className="space-y-4 overflow-x-auto pb-4">
                                                        <div className="grid grid-cols-12 gap-4 items-center bg-slate-50 p-3 rounded-lg border border-slate-100 font-semibold text-xs text-slate-500 uppercase tracking-wider min-w-[600px]">
                                                            <div className="col-span-4">Parameter</div>
                                                            <div className="col-span-3">Result Value</div>
                                                            <div className="col-span-2">Unit</div>
                                                            <div className="col-span-2">Ref. Range</div>
                                                            <div className="col-span-1 text-center">Flag</div>
                                                        </div>

                                                        {[
                                                            { key: 'wbc', name: 'White Blood Cells (WBC)', unit: 'x10^9/L', min: 4.0, max: 11.0 },
                                                            { key: 'hgb', name: 'Hemoglobin (HGB)', unit: 'g/dL', min: 12.0, max: 16.0 },
                                                        ].map(param => (
                                                            <div key={param.key} className="grid grid-cols-12 gap-4 items-center border-b border-slate-50 pb-2 min-w-[600px]">
                                                                <div className="col-span-4 font-bold text-sm text-slate-700">{param.name}</div>
                                                                <div className="col-span-3">
                                                                    <input 
                                                                        type="number" step="0.1"
                                                                        value={results[param.key] || ''}
                                                                        onChange={(e) => setResults({...results, [param.key]: e.target.value})}
                                                                        className="w-full px-3 py-2 border border-slate-200 rounded-md text-sm focus:ring-2 focus:ring-brand-500 outline-none" 
                                                                    />
                                                                </div>
                                                                <div className="col-span-2 text-sm text-slate-500">{param.unit}</div>
                                                                <div className="col-span-2 text-xs font-mono text-slate-400">{param.min} - {param.max}</div>
                                                                <div className="col-span-1 flex justify-center">
                                                                    {getFlag(results[param.key], param.min, param.max)}
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <div>
                                                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Qualitative Result / Impression</label>
                                                        <textarea 
                                                            rows="3" 
                                                            value={results.qualitative || ''}
                                                            onChange={(e) => setResults({ qualitative: e.target.value })}
                                                            className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" 
                                                            placeholder="Enter qualitative findings..."
                                                        ></textarea>
                                                    </div>
                                                )}
                                                
                                                <div className="mt-4">
                                                    <label className="block text-xs font-bold text-slate-700 mb-1.5">Technician Notes (Optional)</label>
                                                    <input type="text" value={techNotes} onChange={(e) => setTechNotes(e.target.value)} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none bg-slate-50" placeholder="Methodology notes..." />
                                                </div>
                                            </div>

                                            {/* STEP 2: INVENTORY CONSUMPTION TRACKER */}
                                            <div className="bg-white border-l-4 border-orange-400 rounded-r-xl border-y border-r border-slate-200 p-6 shadow-sm">
                                                <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 flex items-center gap-2 border-b border-slate-100 pb-3">
                                                    <Package className="text-orange-500" size={18} /> Reagents & Consumables Used
                                                </h3>
                                                
                                                <div className="flex gap-3 mb-4">
                                                    <select 
                                                        value={selectedBatchId} 
                                                        onChange={(e) => setSelectedBatchId(e.target.value)}
                                                        className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none"
                                                    >
                                                        <option value="">Select item from Lab Store...</option>
                                                        {labInventory.map(item => (
                                                            <option key={item.batch_id} value={item.batch_id}>
                                                                {item.name} (Batch {item.batch_no}) - {item.stock} {item.unit} avail.
                                                            </option>
                                                        ))}
                                                    </select>
                                                    <input 
                                                        type="number" min="1" placeholder="Qty" 
                                                        value={consumeQty} onChange={(e) => setConsumeQty(e.target.value)}
                                                        className="w-24 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" 
                                                    />
                                                    <button onClick={addConsumedItem} className="bg-slate-800 text-white px-4 py-2 rounded-lg text-sm font-bold hover:bg-slate-900 flex items-center gap-1">
                                                        <Plus size={16}/> Add
                                                    </button>
                                                </div>

                                                {consumedItems.length > 0 && (
                                                    <div className="bg-slate-50 border border-slate-200 rounded-lg overflow-x-auto">
                                                        <table className="w-full text-left text-sm text-slate-600 min-w-[400px]">
                                                            <thead className="bg-slate-100 text-slate-500 text-xs uppercase font-bold border-b border-slate-200">
                                                                <tr>
                                                                    <th className="px-4 py-2">Item Name & Batch</th>
                                                                    <th className="px-4 py-2">Qty Used</th>
                                                                    <th className="px-4 py-2"></th>
                                                                </tr>
                                                            </thead>
                                                            <tbody className="divide-y divide-slate-100">
                                                                {consumedItems.map(item => (
                                                                    <tr key={item.batch_id}>
                                                                        <td className="px-4 py-2 font-medium text-slate-900">{item.name} <span className="text-xs text-slate-500">({item.batch_no})</span></td>
                                                                        <td className="px-4 py-2 font-bold">{item.quantity} {item.unit}</td>
                                                                        <td className="px-4 py-2 text-right">
                                                                            <button onClick={() => removeConsumedItem(item.batch_id)} className="text-slate-400 hover:text-red-500"><Trash2 size={16}/></button>
                                                                        </td>
                                                                    </tr>
                                                                ))}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                )}
                                                {consumedItems.length === 0 && <p className="text-xs text-slate-400 italic">No consumables logged. Reagents must be logged to maintain accurate stock levels.</p>}
                                            </div>
                                        </>
                                    )}
                                </div>

                                {/* Workbench Footer Actions */}
                                {activeTest.status === 'In Progress' && (
                                    <div className="p-4 border-t border-slate-200 bg-slate-50 flex justify-end gap-3 shrink-0 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.02)] z-10">
                                        <button className="px-5 py-2.5 bg-white border border-red-200 text-red-600 rounded-lg text-sm font-bold hover:bg-red-50 flex items-center gap-2 transition-colors">
                                            <XCircle size={18} /> Reject Sample
                                        </button>
                                        <button onClick={handleReleaseResults} className="px-6 py-2.5 bg-accent-600 hover:bg-accent-700 text-white rounded-lg text-sm font-bold flex items-center gap-2 shadow-sm transition-colors">
                                            <Send size={18} /> Verify, Release & Deduct Stock
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
                <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm flex flex-col overflow-hidden">
                    <div className="p-6 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
                        <div>
                            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                                <Settings className="text-slate-400" size={20} /> Managed Test Directory
                            </h2>
                            <p className="text-sm text-slate-500 mt-1">This catalog is managed by Hospital Administration and determines what Doctors can order.</p>
                        </div>
                    </div>
                    
                    <div className="flex-1 overflow-auto">
                        <table className="w-full text-left text-sm text-slate-600 min-w-[500px]">
                            <thead className="bg-white text-slate-500 text-xs uppercase font-bold border-b border-slate-200 sticky top-0">
                                <tr>
                                    <th className="px-6 py-4">Test Code & Name</th>
                                    <th className="px-6 py-4">Category</th>
                                    <th className="px-6 py-4">Description / Specimen</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {isLoading ? (
                                    <tr><td colSpan="3" className="text-center py-8">Loading Catalog...</td></tr>
                                ) : catalog.length === 0 ? (
                                    <tr><td colSpan="3" className="text-center py-8 text-slate-500">No Laboratory packages found in Admin Pricing Catalog.</td></tr>
                                ) : catalog.map((test) => (
                                    <tr key={test.catalog_id} className="hover:bg-slate-50 transition-colors">
                                        <td className="px-6 py-4">
                                            <div className="font-bold text-slate-900">{test.test_name}</div>
                                            <div className="text-xs font-mono text-slate-500 mt-0.5">PKG-LAB-{String(test.catalog_id).padStart(4, '0')}</div>
                                        </td>
                                        <td className="px-6 py-4 font-medium text-slate-700">{test.category}</td>
                                        <td className="px-6 py-4">
                                            <span className="bg-slate-100 text-slate-700 px-2.5 py-1 rounded text-xs font-semibold">{test.default_specimen_type || 'General'}</span>
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