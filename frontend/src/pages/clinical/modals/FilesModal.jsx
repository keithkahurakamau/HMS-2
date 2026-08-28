import React, { useState, useEffect, useRef } from 'react';
import { Paperclip, Upload, Download, Trash2, FileText } from 'lucide-react';
import toast from 'react-hot-toast';
import Modal from './Modal';
import { listFiles, uploadFile, downloadFile, deleteFile } from '../../../api/clinicalFiles';

const MAX_BYTES = 2 * 1024 * 1024; // 2 MB binary: matches the server's ~2.8 MB base64 cap.
const err = (e, fallback) => toast.error(e?.response?.data?.detail || fallback);

const prettySize = (bytes) => {
    if (!bytes) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
};

const readAsDataUrl = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
});

// Pure: fetches the file blob then triggers a browser download. No component
// state, so it lives at module scope.
const downloadAttachment = (f) => {
    downloadFile(f.file_id)
        .then((full) => {
            const a = document.createElement('a');
            a.href = full.data;
            a.download = full.filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
        })
        .catch((e) => err(e, 'Could not download file.'));
};

/**
 * Patient file attachments: upload documents/images, list them, download or
 * delete. Files are stored base64-in-DB; the size guard mirrors the server cap.
 * `recordId` (optional) links an upload to the current encounter.
 */
export default function FilesModal({ patient, recordId = null, onClose }) {
    const [files, setFiles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const inputRef = useRef(null);

    const load = () => {
        listFiles(patient.patient_id)
            .then((rows) => setFiles(rows || []))
            .catch((e) => err(e, 'Could not load attachments.'))
            .finally(() => setLoading(false));
    };
    useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

    const onPick = (e) => {
        const file = e.target.files?.[0];
        if (inputRef.current) inputRef.current.value = ''; // allow re-picking the same file
        if (!file) return;
        if (file.size > MAX_BYTES) { toast.error('File too large: max 2 MB per attachment.'); return; }
        setUploading(true);
        readAsDataUrl(file)
            .then((data) => uploadFile({
                patient_id: patient.patient_id, filename: file.name,
                mime: file.type || null, data, record_id: recordId,
            }))
            .then(() => { toast.success('File attached.'); load(); })
            .catch((e) => err(e, 'Could not upload file.'))
            .finally(() => setUploading(false));
    };

    const onDelete = (f) => {
        deleteFile(f.file_id)
            .then(() => { toast.success('Attachment removed.'); load(); })
            .catch((e) => err(e, 'Could not delete file.'));
    };

    return (
        <Modal title="Attachments" icon={Paperclip} onClose={onClose}
            footer={<button type="button" onClick={onClose} className="btn-secondary">Close</button>}>
            <p className="text-xs text-ink-500 dark:text-ink-400">
                Documents &amp; images for <span className="font-semibold text-ink-800 dark:text-ink-200">{patient.patient_name}</span>
            </p>

            <div>
                <input ref={inputRef} type="file" className="hidden" onChange={onPick}
                    aria-label="Choose a file to attach" />
                <button type="button" disabled={uploading} onClick={() => inputRef.current?.click()}
                    className="btn-secondary text-xs">
                    <Upload size={14} /> {uploading ? 'Uploading…' : 'Upload file'}
                </button>
                <span className="ml-2 text-2xs text-ink-400 dark:text-ink-500">Max 2 MB per file</span>
            </div>

            {loading ? (
                <p className="text-sm text-ink-500 dark:text-ink-400">Loading…</p>
            ) : files.length === 0 ? (
                <p className="text-sm text-ink-500 dark:text-ink-400 italic">No attachments yet.</p>
            ) : (
                <ul className="space-y-2">
                    {files.map((f) => (
                        <li key={f.file_id}
                            className="rounded-xl border border-ink-200 dark:border-ink-800 p-3 flex items-center justify-between gap-3">
                            <div className="min-w-0 flex items-center gap-2">
                                <FileText size={15} className="text-ink-400 shrink-0" />
                                <div className="min-w-0">
                                    <p className="text-sm font-medium text-ink-800 dark:text-ink-200 truncate">{f.filename}</p>
                                    <p className="text-2xs text-ink-500 dark:text-ink-400">{prettySize(f.size_bytes)}</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-1 shrink-0">
                                <button type="button" onClick={() => downloadAttachment(f)} aria-label={`Download ${f.filename}`}
                                    className="p-1.5 rounded-lg text-ink-400 hover:bg-ink-100 dark:hover:bg-ink-800"><Download size={15} /></button>
                                <button type="button" onClick={() => onDelete(f)} aria-label={`Delete ${f.filename}`}
                                    className="p-1.5 rounded-lg text-ink-400 hover:text-rose-600 hover:bg-ink-100 dark:hover:bg-ink-800"><Trash2 size={15} /></button>
                            </div>
                        </li>
                    ))}
                </ul>
            )}
        </Modal>
    );
}
