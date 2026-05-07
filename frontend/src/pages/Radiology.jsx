import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
    Radio, Activity, CheckCircle2,
    Bone, FileText, ChevronDown, ChevronUp,
    Send, User, Clock, Image as ImageIcon, FileSearch, Printer
} from 'lucide-react';
import toast from 'react-hot-toast';
import { printRadiologyReport } from '../utils/printTemplates';

export default function Radiology() {
    const [isQueueOpen, setIsQueueOpen] = useState(true);
    const [isLoading, setIsLoading] = useState(true);
    const [queue, setQueue] = useState([]);
    const [activeRequest, setActiveRequest] = useState(null);

    const [findings, setFindings] = useState('');
    const [conclusion, setConclusion] = useState('');
    const [imageUrl, setImageUrl] = useState('');

    useEffect(() => { fetchQueue(); }, []);

    const fetchQueue = async () => {
        setIsLoading(true);
        try {
            const response = await apiClient.get('/radiology/');
            const res = response.data;
            const activeQueue = res.filter(q => q.status !== 'Completed' && q.status !== 'Cancelled');
            setQueue(activeQueue);
        } catch (error) {
            toast.error('Failed to sync radiology queue.');
            setQueue([]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleRequestSelect = (req) => {
        setActiveRequest(req);
        setIsQueueOpen(false);
        setFindings('');
        setConclusion('');
        setImageUrl('');
    };

    const handleAcknowledgePatient = async () => {
        try {
            const response = await apiClient.put(`/radiology/${activeRequest.request_id}/status`, { status: 'In Progress' });
            const updatedReq = response.data;
            setActiveRequest(updatedReq);
            setQueue(queue.map(q => q.request_id === activeRequest.request_id ? updatedReq : q));
            toast.success('Patient acknowledged. Status moved to In Progress.');
        } catch (error) {
            toast.error('Failed to update status.');
        }
    };

    const handleReleaseResults = async () => {
        if (!findings || !conclusion) return toast.error('Findings and conclusion are required.');

        try {
            await apiClient.post(`/radiology/${activeRequest.request_id}/result`, {
                findings, conclusion, image_url: imageUrl || null,
            });
            toast.success('Radiology results published successfully!');

            setQueue(queue.filter(q => q.request_id !== activeRequest.request_id));
            setActiveRequest(null);
            setIsQueueOpen(true);
            fetchQueue();
        } catch (error) {
            toast.error(error.response?.data?.detail || 'Failed to submit results.');
        }
    };

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">
            {/* HEADER */}
            <div className="card p-4 shrink-0">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-brand-50 text-brand-600 flex items-center justify-center ring-1 ring-inset ring-brand-100">
                        <Radio size={20} />
                    </div>
                    <div>
                        <span className="section-eyebrow">Imaging</span>
                        <h1 className="text-lg font-semibold text-ink-900 tracking-tight">Radiology Department</h1>
                        <p className="text-xs font-medium text-ink-500">Manage imaging requests, X-rays, MRIs, and scan results</p>
                    </div>
                </div>
            </div>

            {/* COLLAPSIBLE QUEUE */}
            <div className="card shrink-0 flex flex-col z-20">
                <button onClick={() => setIsQueueOpen(!isQueueOpen)} className="w-full p-4 flex justify-between items-center bg-ink-50/60 hover:bg-brand-50/40 transition-colors rounded-t-2xl focus:outline-none">
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
                            <div className="text-center py-6 text-ink-400"><Activity className="animate-spin mx-auto mb-2 text-brand-500" size={20} /> Syncing queue&hellip;</div>
                        ) : queue.length === 0 ? (
                            <div className="text-center py-6 text-ink-400">No pending imaging requests in queue.</div>
                        ) : (
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                {queue.map((req) => {
                                    const active = activeRequest?.request_id === req.request_id;
                                    return (
                                        <button key={req.request_id} type="button" onClick={() => handleRequestSelect(req)} className={`text-left p-3 rounded-xl border transition-all duration-150 ${active ? 'bg-brand-50/60 border-brand-400 ring-2 ring-brand-500/15' : 'bg-white border-ink-200 hover:border-brand-300 hover:-translate-y-0.5'}`}>
                                            <div className="flex justify-between items-start mb-2">
                                                <h3 className="font-semibold text-sm text-ink-900 line-clamp-1">{req.exam_type}</h3>
                                            </div>
                                            <div className="flex justify-between items-center text-xs text-ink-500 mb-2">
                                                <span className="font-medium text-ink-700 flex items-center gap-1"><User size={12} className="text-ink-400" /> Patient #{req.patient_id}</span>
                                                <span className="font-mono text-2xs text-ink-400">#{req.request_id}</span>
                                            </div>
                                            <div className="flex justify-between items-center text-xs">
                                                <span className={req.status === 'Pending' ? 'badge-warn' : 'badge-info'}>{req.status}</span>
                                                <span className="text-ink-400 flex items-center gap-1"><Clock size={10} /> {new Date(req.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* WORKSPACE */}
            <div className="flex-1 card overflow-hidden flex flex-col z-10 relative">
                {!activeRequest ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-ink-400 bg-ink-50/40">
                        <Bone size={56} className="mb-4 text-ink-300" strokeWidth={1.5} />
                        <h3 className="text-base font-semibold text-ink-600 mb-1">Radiology reading room</h3>
                        <p className="text-sm">Select a pending request from the queue to process imaging and enter results.</p>
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
                                        Patient ID: <span className="text-ink-700">{activeRequest.patient_id}</span> &middot; Ordered by: <span className="text-ink-700">Dr. #{activeRequest.requested_by}</span>
                                    </p>
                                </div>
                                <button
                                    onClick={() => printRadiologyReport({
                                        patient: { full_name: activeRequest.patient_name, outpatient_no: activeRequest.patient_opd },
                                        request: {
                                            request_id: activeRequest.request_id,
                                            modality: activeRequest.modality || activeRequest.exam_type,
                                            body_part: activeRequest.body_part,
                                            clinical_indication: activeRequest.clinical_notes,
                                            status: activeRequest.status,
                                            created_at: activeRequest.created_at,
                                        },
                                        result: (findings || conclusion) ? { findings, impression: conclusion } : null,
                                        radiologist: { full_name: activeRequest.radiologist_name },
                                    })}
                                    className="btn-secondary shrink-0"
                                    title="Print radiology report"
                                >
                                    <Printer size={15} /> Print
                                </button>
                            </div>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-5 bg-ink-50/40 custom-scrollbar">
                            {activeRequest.status === 'Pending' ? (
                                <div className="card p-6 text-center py-12">
                                    <ImageIcon size={44} className="mx-auto text-ink-300 mb-4" />
                                    <h3 className="text-base font-semibold text-ink-800 mb-1">Awaiting patient arrival</h3>
                                    <p className="text-sm text-ink-500 mb-6 max-w-md mx-auto">Please confirm when the patient arrives and the imaging process begins.</p>

                                    {activeRequest.clinical_notes && (
                                        <div className="max-w-md mx-auto bg-amber-50 ring-1 ring-amber-100 p-4 rounded-xl text-left mb-6">
                                            <p className="text-2xs font-semibold text-amber-700 uppercase mb-1 tracking-[0.14em]">Clinical notes / reason for exam</p>
                                            <p className="text-sm text-amber-900 leading-relaxed">{activeRequest.clinical_notes}</p>
                                        </div>
                                    )}

                                    <div className="flex flex-wrap justify-center gap-3">
                                        <button onClick={() => { setActiveRequest(null); setIsQueueOpen(true); }} className="btn-secondary">Cancel</button>
                                        <button onClick={handleAcknowledgePatient} className="btn-primary">
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
                                                <textarea rows="4" value={findings} onChange={(e) => setFindings(e.target.value)} className="input resize-none" placeholder="Enter detailed radiological findings…" />
                                            </div>
                                            <div>
                                                <label className="label">Conclusion / impression</label>
                                                <textarea rows="2" value={conclusion} onChange={(e) => setConclusion(e.target.value)} className="input resize-none" placeholder="Enter summary impression…" />
                                            </div>
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
                                <button onClick={handleReleaseResults} className="btn-success">
                                    <Send size={16} /> Sign & publish report
                                </button>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
