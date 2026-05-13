import React, { useState, useEffect, useMemo } from 'react';
import { apiClient } from '../api/client';
import {
    Radio, Activity, CheckCircle2,
    Bone, FileText, ChevronDown, ChevronUp,
    Send, User, Clock, Image as ImageIcon, FileSearch, Printer,
    Plus, Pencil, Trash2, Save, X, FileDigit, Settings,
} from 'lucide-react';
import toast from 'react-hot-toast';
import { printRadiologyReport } from '../utils/printTemplates';
import PageHeader from '../components/PageHeader';

const EMPTY_CATALOG = {
    exam_name: '', modality: 'X-Ray', body_part: '', description: '',
    base_price: 0, requires_prep: false, requires_contrast: false,
    default_findings_template: '', default_impression_template: '',
    is_active: true,
};

export default function Radiology() {
    const [activeTab, setActiveTab] = useState('queue');
    const [isQueueOpen, setIsQueueOpen] = useState(true);
    const [isLoading, setIsLoading] = useState(true);

    const [queue, setQueue] = useState([]);
    const [catalog, setCatalog] = useState([]);
    const [activeRequest, setActiveRequest] = useState(null);

    const [findings, setFindings] = useState('');
    const [conclusion, setConclusion] = useState('');
    const [imageUrl, setImageUrl] = useState('');
    const [contrastUsed, setContrastUsed] = useState('');

    // Catalog editor
    const [editorOpen, setEditorOpen] = useState(false);
    const [editing, setEditing] = useState(null);
    const [form, setForm] = useState(EMPTY_CATALOG);

    useEffect(() => { fetchData(); }, []);

    const fetchData = async () => {
        setIsLoading(true);
        try {
            const [queueRes, catRes] = await Promise.all([
                apiClient.get('/radiology/').catch(() => ({ data: [] })),
                apiClient.get('/radiology/catalog?include_inactive=true').catch(() => ({ data: [] })),
            ]);
            const active = (queueRes.data || []).filter(q => q.status !== 'Completed' && q.status !== 'Cancelled');
            setQueue(active);
            setCatalog(catRes.data || []);
        } catch {
            toast.error('Failed to sync radiology data.');
            setQueue([]); setCatalog([]);
        } finally {
            setIsLoading(false);
        }
    };

    const activeCatalog = useMemo(
        () => catalog.find(c => c.catalog_id === activeRequest?.catalog_id),
        [catalog, activeRequest],
    );

    const handleSelect = (req) => {
        setActiveRequest(req);
        setIsQueueOpen(false);
        const cat = catalog.find(c => c.catalog_id === req.catalog_id);
        setFindings(cat?.default_findings_template || '');
        setConclusion(cat?.default_impression_template || '');
        setImageUrl('');
        setContrastUsed('');
    };

    const handleAcknowledge = async () => {
        try {
            const res = await apiClient.put(`/radiology/${activeRequest.request_id}/status`, { status: 'In Progress' });
            setActiveRequest(res.data);
            setQueue(queue.map(q => q.request_id === activeRequest.request_id ? res.data : q));
            toast.success('Patient acknowledged — exam in progress.');
        } catch {
            toast.error('Failed to update status.');
        }
    };

    const handleRelease = async () => {
        if (!findings || !conclusion) return toast.error('Findings and conclusion are required.');
        try {
            await apiClient.post(`/radiology/${activeRequest.request_id}/result`, {
                findings, conclusion,
                image_url: imageUrl || null,
                contrast_used: contrastUsed || null,
            });
            toast.success('Radiology results published.');
            setQueue(queue.filter(q => q.request_id !== activeRequest.request_id));
            setActiveRequest(null);
            setIsQueueOpen(true);
            fetchData();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Failed to submit results.');
        }
    };

    /* ── Catalog editor ─────────────────────────────────────────────────── */

    const startCreate = () => { setEditing(null); setForm(EMPTY_CATALOG); setEditorOpen(true); };
    const startEdit = (row) => {
        setEditing(row);
        setForm({ ...EMPTY_CATALOG, ...row, base_price: Number(row.base_price || 0) });
        setEditorOpen(true);
    };

    const save = async () => {
        const body = { ...form, base_price: parseFloat(form.base_price) || 0 };
        try {
            if (editing) {
                await apiClient.patch(`/radiology/catalog/${editing.catalog_id}`, body);
                toast.success('Catalog entry updated.');
            } else {
                await apiClient.post('/radiology/catalog', body);
                toast.success('Catalog entry created.');
            }
            setEditorOpen(false);
            fetchData();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Save failed.');
        }
    };

    const deactivate = async (row) => {
        if (!window.confirm(`Deactivate "${row.exam_name}"?`)) return;
        try {
            await apiClient.delete(`/radiology/catalog/${row.catalog_id}`);
            toast.success(`${row.exam_name} deactivated.`);
            fetchData();
        } catch (e) {
            toast.error(e.response?.data?.detail || 'Deactivation failed.');
        }
    };

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">
            <PageHeader
                eyebrow="Imaging"
                icon={Radio}
                title="Radiology"
                subtitle="Acquire imaging requests, run studies, and publish reports."
            />
            <div className="card p-2 flex items-center justify-between shrink-0">
                <div role="tablist" className="flex bg-ink-100/70 p-1 rounded-xl w-full max-w-md">
                    <button role="tab" aria-selected={activeTab === 'queue'} onClick={() => setActiveTab('queue')}
                            className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium transition-all ${activeTab === 'queue' ? 'bg-white text-ink-900 shadow-soft ring-1 ring-ink-200/70' : 'text-ink-600 hover:text-ink-900'}`}>
                        <Radio size={16} className={activeTab === 'queue' ? 'text-brand-600' : 'text-ink-400'} /> Reading room
                    </button>
                    <button role="tab" aria-selected={activeTab === 'catalog'} onClick={() => setActiveTab('catalog')}
                            className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium transition-all ${activeTab === 'catalog' ? 'bg-white text-ink-900 shadow-soft ring-1 ring-ink-200/70' : 'text-ink-600 hover:text-ink-900'}`}>
                        <FileDigit size={16} className={activeTab === 'catalog' ? 'text-accent-600' : 'text-ink-400'} /> Exam Catalog
                    </button>
                </div>
            </div>

            {activeTab === 'queue' && (
                <>
                    {/* Queue */}
                    <div className="card shrink-0 flex flex-col z-20">
                        <button onClick={() => setIsQueueOpen(!isQueueOpen)} className="w-full p-4 flex justify-between items-center bg-ink-50/60 hover:bg-brand-50/40 transition-colors rounded-t-2xl">
                            <div className="flex items-center gap-3">
                                <Activity className="text-brand-600" size={18} />
                                <h2 className="font-semibold text-ink-900 text-base tracking-tight">Pending imaging requests</h2>
                                <span className="badge-brand">{queue.length} Requests</span>
                            </div>
                            <span className="text-ink-500">{isQueueOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</span>
                        </button>

                        {isQueueOpen && (
                            <div className="border-t border-ink-100 p-4 bg-white rounded-b-2xl">
                                {isLoading ? (
                                    <div className="text-center py-6 text-ink-400"><Activity className="animate-spin mx-auto mb-2 text-brand-500" size={20} /> Syncing queue…</div>
                                ) : queue.length === 0 ? (
                                    <div className="text-center py-6 text-ink-400">No pending imaging requests.</div>
                                ) : (
                                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                        {queue.map((req) => {
                                            const active = activeRequest?.request_id === req.request_id;
                                            return (
                                                <button key={req.request_id} type="button" onClick={() => handleSelect(req)}
                                                        className={`text-left p-3 rounded-xl border transition-all duration-150 ${active ? 'bg-brand-50/60 border-brand-400 ring-2 ring-brand-500/15' : 'bg-white border-ink-200 hover:border-brand-300 hover:-translate-y-0.5'}`}>
                                                    <div className="flex justify-between items-start mb-2">
                                                        <h3 className="font-semibold text-sm text-ink-900 line-clamp-1">{req.exam_type}</h3>
                                                        {req.priority === 'STAT' && <span className="badge-danger text-2xs">STAT</span>}
                                                    </div>
                                                    <div className="flex justify-between items-center text-xs text-ink-500 mb-2">
                                                        <span className="font-medium text-ink-700 flex items-center gap-1"><User size={12} /> #{req.patient_id}</span>
                                                        <span className="font-mono text-2xs text-ink-400">#{req.request_id}</span>
                                                    </div>
                                                    <div className="flex justify-between items-center text-xs">
                                                        <span className={req.status === 'Pending' ? 'badge-warn' : 'badge-info'}>{req.status}</span>
                                                        <span className="text-ink-400 flex items-center gap-1"><Clock size={10} /> {new Date(req.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                                                    </div>
                                                </button>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Workspace */}
                    <div className="flex-1 card overflow-hidden flex flex-col z-10 relative">
                        {!activeRequest ? (
                            <div className="flex-1 flex flex-col items-center justify-center text-ink-400 bg-ink-50/40">
                                <Bone size={56} className="mb-4 text-ink-300" strokeWidth={1.5} />
                                <h3 className="text-base font-semibold text-ink-600 mb-1">Radiology reading room</h3>
                                <p className="text-sm">Select a pending request to enter findings.</p>
                            </div>
                        ) : (
                            <>
                                <div className="shrink-0 p-5 border-b border-ink-100 bg-white flex justify-between items-center z-10">
                                    <div className="flex gap-3 items-center flex-1 min-w-0">
                                        <div className="w-11 h-11 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center ring-1 ring-inset ring-brand-100">
                                            <Bone size={20} />
                                        </div>
                                        <div className="flex-1 min-w-0">
                                            <h1 className="text-lg font-semibold text-ink-900 tracking-tight truncate">{activeRequest.exam_type}</h1>
                                            <p className="text-xs font-medium text-ink-500 truncate">
                                                Patient ID: <span className="text-ink-700">{activeRequest.patient_id}</span> ·
                                                Ordered by: <span className="text-ink-700">Dr. #{activeRequest.requested_by}</span>
                                                {activeCatalog && <> · <span className="text-ink-700">{activeCatalog.modality}{activeCatalog.body_part ? ` · ${activeCatalog.body_part}` : ''}</span></>}
                                            </p>
                                        </div>
                                        <button onClick={() => printRadiologyReport({
                                            patient: { full_name: activeRequest.patient_name, outpatient_no: activeRequest.patient_opd },
                                            request: {
                                                request_id: activeRequest.request_id,
                                                modality: activeCatalog?.modality || activeRequest.exam_type,
                                                body_part: activeCatalog?.body_part,
                                                clinical_indication: activeRequest.clinical_notes,
                                                status: activeRequest.status,
                                                created_at: activeRequest.created_at,
                                            },
                                            result: (findings || conclusion) ? { findings, impression: conclusion } : null,
                                            radiologist: { full_name: activeRequest.radiologist_name },
                                        })} className="btn-secondary shrink-0" title="Print radiology report">
                                            <Printer size={15} /> Print
                                        </button>
                                    </div>
                                </div>

                                <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-5 bg-ink-50/40 custom-scrollbar">
                                    {activeRequest.status === 'Pending' ? (
                                        <div className="card p-6 text-center py-12">
                                            <ImageIcon size={44} className="mx-auto text-ink-300 mb-4" />
                                            <h3 className="text-base font-semibold text-ink-800 mb-1">Awaiting patient arrival</h3>
                                            <p className="text-sm text-ink-500 mb-6 max-w-md mx-auto">Confirm when the patient arrives and imaging begins.</p>

                                            {activeCatalog?.requires_prep && (
                                                <div className="max-w-md mx-auto bg-rose-50 ring-1 ring-rose-100 p-3 rounded-xl text-left mb-4">
                                                    <p className="text-2xs font-semibold text-rose-700 uppercase tracking-[0.14em]">⚠ Patient prep required</p>
                                                    <p className="text-sm text-rose-900 leading-relaxed mt-1">Verify fasting / hydration / clothing instructions for this exam.</p>
                                                </div>
                                            )}

                                            {activeRequest.clinical_notes && (
                                                <div className="max-w-md mx-auto bg-amber-50 ring-1 ring-amber-100 p-4 rounded-xl text-left mb-6">
                                                    <p className="text-2xs font-semibold text-amber-700 uppercase mb-1 tracking-[0.14em]">Clinical notes / reason for exam</p>
                                                    <p className="text-sm text-amber-900 leading-relaxed">{activeRequest.clinical_notes}</p>
                                                </div>
                                            )}

                                            <div className="flex flex-wrap justify-center gap-3">
                                                <button onClick={() => { setActiveRequest(null); setIsQueueOpen(true); }} className="btn-secondary">Cancel</button>
                                                <button onClick={handleAcknowledge} className="btn-primary">
                                                    <CheckCircle2 size={16} /> Acknowledge & begin exam
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <>
                                            {activeRequest.clinical_notes && (
                                                <div className="bg-amber-50 ring-1 ring-amber-100 p-4 rounded-xl">
                                                    <p className="text-2xs font-semibold text-amber-700 uppercase mb-1 tracking-[0.14em] flex items-center gap-2">
                                                        <FileSearch size={13} /> Clinical notes / indication
                                                    </p>
                                                    <p className="text-sm text-amber-900 leading-relaxed">{activeRequest.clinical_notes}</p>
                                                </div>
                                            )}

                                            <div className="card-flush p-5 sm:p-6 animate-fade-in">
                                                <h3 className="section-eyebrow mb-5 border-b border-ink-100 pb-3 flex items-center gap-2">
                                                    <FileText className="text-brand-600" size={16} /> Radiologist report
                                                </h3>
                                                <div className="space-y-4">
                                                    <div>
                                                        <label className="label">Detailed findings</label>
                                                        <textarea rows="5" value={findings} onChange={(e) => setFindings(e.target.value)} className="input resize-none" placeholder="Enter detailed radiological findings…" />
                                                    </div>
                                                    <div>
                                                        <label className="label">Conclusion / impression</label>
                                                        <textarea rows="3" value={conclusion} onChange={(e) => setConclusion(e.target.value)} className="input resize-none" placeholder="Enter summary impression…" />
                                                    </div>
                                                    {activeCatalog?.requires_contrast && (
                                                        <div>
                                                            <label className="label">Contrast used</label>
                                                            <input type="text" value={contrastUsed} onChange={(e) => setContrastUsed(e.target.value)} className="input" placeholder="e.g. Iohexol 100 mL IV" />
                                                        </div>
                                                    )}
                                                    <div>
                                                        <label className="label">Attach image / DICOM URL (optional)</label>
                                                        <div className="relative">
                                                            <ImageIcon size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                                                            <input type="text" value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} className="input pl-10" placeholder="https://pacs.internal/images/…" />
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </>
                                    )}
                                </div>

                                {activeRequest.status === 'In Progress' && (
                                    <div className="p-4 border-t border-ink-100 bg-white flex justify-end gap-2 shrink-0 z-10">
                                        <button onClick={() => { setActiveRequest(null); setIsQueueOpen(true); }} className="btn-secondary">Close</button>
                                        <button onClick={handleRelease} className="btn-success">
                                            <Send size={16} /> Sign & publish report
                                        </button>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                </>
            )}

            {activeTab === 'catalog' && (
                <div className="flex-1 card flex flex-col overflow-hidden">
                    <div className="p-5 border-b border-ink-100 bg-ink-50/40 flex justify-between items-center flex-wrap gap-3">
                        <div>
                            <span className="section-eyebrow">Admin</span>
                            <h2 className="text-base font-semibold text-ink-900 mt-1 flex items-center gap-2 tracking-tight">
                                <Settings className="text-ink-400" size={18} /> Exam directory
                            </h2>
                            <p className="text-sm text-ink-500 mt-1">Add or revise exams, default templates and pricing.</p>
                        </div>
                        <button onClick={startCreate} className="btn-primary"><Plus size={16} /> New exam</button>
                    </div>

                    <div className="flex-1 overflow-auto">
                        <table className="table-clean min-w-[700px]">
                            <thead>
                                <tr>
                                    <th>Exam</th>
                                    <th>Modality</th>
                                    <th>Body part</th>
                                    <th>Price</th>
                                    <th>Prep</th>
                                    <th>Contrast</th>
                                    <th>Status</th>
                                    <th className="text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {isLoading ? (
                                    <tr><td colSpan="8" className="text-center py-8 text-ink-400">Loading…</td></tr>
                                ) : catalog.length === 0 ? (
                                    <tr><td colSpan="8" className="text-center py-8 text-ink-500">No exams configured. Click "New exam" to add one.</td></tr>
                                ) : catalog.map(row => (
                                    <tr key={row.catalog_id} className={!row.is_active ? 'opacity-50' : ''}>
                                        <td className="font-semibold text-ink-900">{row.exam_name}</td>
                                        <td>{row.modality}</td>
                                        <td>{row.body_part || '—'}</td>
                                        <td className="font-mono">{Number(row.base_price || 0).toFixed(2)}</td>
                                        <td>{row.requires_prep ? <span className="badge-warn text-2xs">Yes</span> : <span className="badge-neutral text-2xs">No</span>}</td>
                                        <td>{row.requires_contrast ? <span className="badge-warn text-2xs">Yes</span> : <span className="badge-neutral text-2xs">No</span>}</td>
                                        <td>{row.is_active ? <span className="badge-success text-2xs">Active</span> : <span className="badge-neutral text-2xs">Inactive</span>}</td>
                                        <td className="text-right">
                                            <button onClick={() => startEdit(row)} className="text-brand-600 hover:text-brand-800 p-1.5" aria-label="Edit"><Pencil size={15} /></button>
                                            {row.is_active && (
                                                <button onClick={() => deactivate(row)} className="text-rose-600 hover:text-rose-800 p-1.5 ml-1" aria-label="Deactivate"><Trash2 size={15} /></button>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {editorOpen && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <div className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setEditorOpen(false)} />
                    <div className="relative w-full max-w-2xl bg-white h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="flex items-center justify-between p-5 border-b border-ink-100 shrink-0">
                            <div>
                                <span className="section-eyebrow">{editing ? 'Edit exam' : 'New exam'}</span>
                                <h2 className="text-xl font-semibold text-ink-900 mt-1 flex items-center gap-2">
                                    <Bone size={20} className="text-brand-600" />
                                    {editing ? `Editing ${editing.exam_name}` : 'Configure a new exam'}
                                </h2>
                            </div>
                            <button onClick={() => setEditorOpen(false)} aria-label="Close" className="text-ink-400 hover:text-ink-700 p-2 hover:bg-ink-100 rounded-full">
                                <X size={20} />
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 bg-ink-50/60 custom-scrollbar space-y-5">
                            <div className="card p-5 space-y-4">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div>
                                        <label className="label">Exam name *</label>
                                        <input className="input" value={form.exam_name}
                                               onChange={e => setForm({ ...form, exam_name: e.target.value })} />
                                    </div>
                                    <div>
                                        <label className="label">Modality *</label>
                                        <select className="input" value={form.modality}
                                                onChange={e => setForm({ ...form, modality: e.target.value })}>
                                            {['X-Ray', 'CT', 'MRI', 'Ultrasound', 'Mammography', 'Fluoroscopy', 'Nuclear Medicine', 'Other'].map(m => <option key={m}>{m}</option>)}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="label">Body part</label>
                                        <input className="input" value={form.body_part || ''}
                                               onChange={e => setForm({ ...form, body_part: e.target.value })}
                                               placeholder="Chest, Abdomen, Right Knee…" />
                                    </div>
                                    <div>
                                        <label className="label">Base price</label>
                                        <input type="number" min="0" step="0.01" className="input" value={form.base_price}
                                               onChange={e => setForm({ ...form, base_price: e.target.value })} />
                                    </div>
                                </div>

                                <div className="flex flex-wrap gap-6">
                                    <label className="flex items-center gap-2 text-sm">
                                        <input type="checkbox" checked={form.is_active}
                                               onChange={e => setForm({ ...form, is_active: e.target.checked })} />
                                        Active
                                    </label>
                                    <label className="flex items-center gap-2 text-sm">
                                        <input type="checkbox" checked={form.requires_prep}
                                               onChange={e => setForm({ ...form, requires_prep: e.target.checked })} />
                                        Requires patient prep
                                    </label>
                                    <label className="flex items-center gap-2 text-sm">
                                        <input type="checkbox" checked={form.requires_contrast}
                                               onChange={e => setForm({ ...form, requires_contrast: e.target.checked })} />
                                        Uses contrast
                                    </label>
                                </div>

                                <div>
                                    <label className="label">Description</label>
                                    <textarea rows="2" className="input resize-none" value={form.description || ''}
                                              onChange={e => setForm({ ...form, description: e.target.value })} />
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div>
                                        <label className="label">Default findings template</label>
                                        <textarea rows="4" className="input resize-none" value={form.default_findings_template || ''}
                                                  onChange={e => setForm({ ...form, default_findings_template: e.target.value })}
                                                  placeholder="Pre-populated for the radiologist…" />
                                    </div>
                                    <div>
                                        <label className="label">Default impression template</label>
                                        <textarea rows="4" className="input resize-none" value={form.default_impression_template || ''}
                                                  onChange={e => setForm({ ...form, default_impression_template: e.target.value })} />
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div className="p-4 border-t border-ink-100 bg-white flex justify-end gap-2 shrink-0">
                            <button onClick={() => setEditorOpen(false)} className="btn-secondary">Cancel</button>
                            <button onClick={save} className="btn-primary"><Save size={15} /> Save</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
