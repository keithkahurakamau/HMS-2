import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { 
    Radio, Activity, CheckCircle2, 
    XCircle, Bone, FileText, ChevronDown, ChevronUp,
    Send, User, Clock, Image as ImageIcon, FileSearch
} from 'lucide-react';
import toast from 'react-hot-toast';

export default function Radiology() {
    const [isQueueOpen, setIsQueueOpen] = useState(true);
    const [isLoading, setIsLoading] = useState(true);
    const [queue, setQueue] = useState([]);
    const [activeRequest, setActiveRequest] = useState(null);

    // Form states
    const [findings, setFindings] = useState('');
    const [conclusion, setConclusion] = useState('');
    const [imageUrl, setImageUrl] = useState('');

    useEffect(() => {
        fetchQueue();
    }, []);

    const fetchQueue = async () => {
        setIsLoading(true);
        try {
            // Fetch all requests (Pending and In Progress)
            const response = await apiClient.get('/radiology/');
            const res = response.data;
            // Filter out completed ones for the active queue
            const activeQueue = res.filter(q => q.status !== 'Completed' && q.status !== 'Cancelled');
            setQueue(activeQueue);
        } catch (error) {
            toast.error("Failed to sync Radiology Queue.");
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
            toast.success("Patient acknowledged. Status moved to In Progress.");
        } catch (error) {
            toast.error("Failed to update status.");
        }
    };

    const handleReleaseResults = async () => {
        if (!findings || !conclusion) {
            toast.error("Findings and Conclusion are required.");
            return;
        }

        try {
            await apiClient.post(`/radiology/${activeRequest.request_id}/result`, {
                findings,
                conclusion,
                image_url: imageUrl || null
            });
            toast.success("Radiology Results Published Successfully!");
            
            setQueue(queue.filter(q => q.request_id !== activeRequest.request_id));
            setActiveRequest(null);
            setIsQueueOpen(true);
            fetchQueue();
        } catch (error) {
            toast.error(error.response?.data?.detail || "Failed to submit results.");
        }
    };

    return (
        <div className="flex flex-col gap-4 h-full md:h-[calc(100vh-8rem)] min-h-[calc(100vh-8rem)]">
            
            {/* RADIOLOGY HEADER */}
            <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm shrink-0">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-brand-50 text-brand-600 rounded-lg flex items-center justify-center border border-brand-100">
                        <Radio size={22} />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold text-slate-900">Radiology Department</h1>
                        <p className="text-sm font-medium text-slate-500">Manage imaging requests, X-Rays, MRIs, and scan results</p>
                    </div>
                </div>
            </div>

            {/* COLLAPSIBLE QUEUE */}
            <div className="bg-white border border-slate-200 rounded-xl shadow-sm shrink-0 flex flex-col z-30">
                <button onClick={() => setIsQueueOpen(!isQueueOpen)} className="w-full p-4 flex justify-between items-center bg-slate-50 hover:bg-brand-50 transition-colors rounded-t-xl focus:outline-none">
                    <div className="flex items-center gap-3">
                        <Activity className="text-brand-600" size={20} />
                        <h2 className="font-bold text-slate-800 text-lg">Pending Imaging Requests</h2>
                        <span className="bg-brand-100 text-brand-700 text-xs font-bold px-2.5 py-1 rounded-full">{queue.length} Requests</span>
                    </div>
                    <div className="flex items-center gap-2 text-slate-500 text-sm font-medium">
                        {isQueueOpen ? <ChevronUp size={20} /> : <ChevronDown size={20} />}
                    </div>
                </button>

                {isQueueOpen && (
                    <div className="border-t border-slate-100 p-4 bg-white rounded-b-xl">
                        {isLoading ? (
                            <div className="text-center py-6 text-slate-400"><Activity className="animate-spin mx-auto mb-2 text-brand-500" /> Syncing Queue...</div>
                        ) : queue.length === 0 ? (
                            <div className="text-center py-6 text-slate-400">No pending imaging requests in queue.</div>
                        ) : (
                            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
                                {queue.map((req) => (
                                    <div key={req.request_id} onClick={() => handleRequestSelect(req)} className={`p-3 rounded-lg border cursor-pointer transition-all ${activeRequest?.request_id === req.request_id ? 'bg-brand-50 border-brand-500 shadow-sm ring-1 ring-brand-500' : 'bg-white hover:border-brand-300'}`}>
                                        <div className="flex justify-between items-start mb-2">
                                            <h3 className="font-bold text-sm text-slate-900 line-clamp-1">{req.exam_type}</h3>
                                        </div>
                                        <div className="flex justify-between items-center text-xs text-slate-500 mb-2">
                                            <span className="font-semibold text-slate-700 flex items-center gap-1"><User size={12}/> Patient #{req.patient_id}</span>
                                            <span className="font-mono text-slate-400">Req:{req.request_id}</span>
                                        </div>
                                        <div className="flex justify-between items-center text-xs">
                                            <span className={`px-2 py-0.5 rounded font-bold ${req.status === 'Pending' ? 'bg-orange-50 text-orange-600' : 'bg-blue-50 text-blue-600'}`}>{req.status}</span>
                                            <span className="text-slate-400 flex items-center gap-1"><Clock size={10} /> {new Date(req.created_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* RADIOLOGY WORKSPACE */}
            <div className="flex-1 bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden flex flex-col z-10 relative">
                {!activeRequest ? (
                    <div className="flex-1 flex flex-col items-center justify-center text-slate-400 bg-slate-50/50">
                        <Bone size={64} className="mb-4 text-slate-300" strokeWidth={1.5} />
                        <h3 className="text-lg font-semibold text-slate-600 mb-1">Radiology Reading Room</h3>
                        <p className="text-sm">Select a pending request from the queue to process imaging and enter results.</p>
                    </div>
                ) : (
                    <>
                        {/* Workspace Header */}
                        <div className="shrink-0 p-5 border-b border-slate-200 bg-white flex justify-between items-center shadow-[0_2px_4px_rgba(0,0,0,0.02)] z-10">
                            <div className="flex gap-4 items-center">
                                <div className="w-12 h-12 bg-brand-50 text-brand-600 rounded-lg flex items-center justify-center border border-brand-100">
                                    <Bone size={24} />
                                </div>
                                <div>
                                    <div className="flex items-center gap-2 mb-1">
                                        <h1 className="text-xl font-bold text-slate-900">{activeRequest.exam_type}</h1>
                                    </div>
                                    <p className="text-sm font-medium text-slate-500">
                                        Patient ID: <span className="text-slate-700">{activeRequest.patient_id}</span> • Ordered by: <span className="text-slate-700">Dr. #{activeRequest.requested_by}</span>
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* Workspace Body */}
                        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50/50">
                            
                            {activeRequest.status === 'Pending' ? (
                                <div className="bg-white border border-slate-200 p-6 rounded-xl shadow-sm text-center py-12">
                                    <ImageIcon size={48} className="mx-auto text-slate-300 mb-4" />
                                    <h3 className="text-lg font-bold text-slate-800 mb-2">Awaiting Patient Arrival</h3>
                                    <p className="text-sm text-slate-500 mb-6 max-w-md mx-auto">Please confirm when the patient arrives and the imaging process begins.</p>
                                    
                                    {activeRequest.clinical_notes && (
                                        <div className="max-w-md mx-auto bg-slate-50 border border-slate-200 p-4 rounded-lg text-left mb-6">
                                            <p className="text-xs font-bold text-slate-500 uppercase mb-1">Clinical Notes / Reason for Exam:</p>
                                            <p className="text-sm text-slate-700">{activeRequest.clinical_notes}</p>
                                        </div>
                                    )}

                                    <div className="flex justify-center gap-4">
                                        <button onClick={() => { setActiveRequest(null); setIsQueueOpen(true); }} className="px-6 py-2.5 border border-slate-200 text-slate-600 hover:bg-slate-50 rounded-lg text-sm font-bold flex items-center gap-2">
                                            Cancel
                                        </button>
                                        <button onClick={handleAcknowledgePatient} className="px-6 py-2.5 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-sm font-bold flex items-center gap-2 shadow-sm">
                                            <CheckCircle2 size={18} /> Acknowledge & Begin Exam
                                        </button>
                                    </div>
                                </div>
                            ) : (
                                <>
                                    {/* Clinical Context */}
                                    {activeRequest.clinical_notes && (
                                        <div className="bg-amber-50 border border-amber-200 p-4 rounded-xl shadow-sm">
                                            <p className="text-xs font-bold text-amber-800 uppercase mb-1 flex items-center gap-2">
                                                <FileSearch size={14} /> Clinical Notes / Indication
                                            </p>
                                            <p className="text-sm text-amber-900">{activeRequest.clinical_notes}</p>
                                        </div>
                                    )}

                                    {/* Results Entry */}
                                    <div className="bg-white border border-slate-200 p-6 rounded-xl shadow-sm animate-in fade-in slide-in-from-bottom-4">
                                        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-6 flex items-center gap-2 border-b border-slate-100 pb-3">
                                            <FileText className="text-brand-600" size={18} /> Radiologist Report
                                        </h3>

                                        <div className="space-y-4">
                                            <div>
                                                <label className="block text-sm font-bold text-slate-700 mb-1.5">Detailed Findings</label>
                                                <textarea 
                                                    rows="4" 
                                                    value={findings}
                                                    onChange={(e) => setFindings(e.target.value)}
                                                    className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" 
                                                    placeholder="Enter detailed radiological findings..."
                                                ></textarea>
                                            </div>

                                            <div>
                                                <label className="block text-sm font-bold text-slate-700 mb-1.5">Conclusion / Impression</label>
                                                <textarea 
                                                    rows="2" 
                                                    value={conclusion}
                                                    onChange={(e) => setConclusion(e.target.value)}
                                                    className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" 
                                                    placeholder="Enter summary impression..."
                                                ></textarea>
                                            </div>

                                            <div>
                                                <label className="block text-sm font-bold text-slate-700 mb-1.5">Attach Image / DICOM URL (Optional)</label>
                                                <div className="flex relative">
                                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                                        <ImageIcon size={16} className="text-slate-400" />
                                                    </div>
                                                    <input 
                                                        type="text" 
                                                        value={imageUrl}
                                                        onChange={(e) => setImageUrl(e.target.value)}
                                                        className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" 
                                                        placeholder="https://pacs.internal/images/..." 
                                                    />
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>

                        {/* Workbench Footer Actions */}
                        {activeRequest.status === 'In Progress' && (
                            <div className="p-4 border-t border-slate-200 bg-slate-50 flex justify-end gap-3 shrink-0 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.02)] z-10">
                                <button onClick={() => { setActiveRequest(null); setIsQueueOpen(true); }} className="px-5 py-2.5 bg-white border border-slate-200 text-slate-600 rounded-lg text-sm font-bold hover:bg-slate-50 transition-colors">
                                    Close
                                </button>
                                <button onClick={handleReleaseResults} className="px-6 py-2.5 bg-accent-600 hover:bg-accent-700 text-white rounded-lg text-sm font-bold flex items-center gap-2 shadow-sm transition-colors">
                                    <Send size={18} /> Sign & Publish Report
                                </button>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
