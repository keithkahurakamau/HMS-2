import { apiClient } from './client';

/**
 * Thin wrappers over the /clinical-files router (base64-in-DB attachments).
 * List returns metadata only; download fetches the data blob for one file.
 */
export const listFiles = (patientId) =>
    apiClient.get('/clinical-files', { params: { patient_id: patientId } }).then((r) => r.data);

export const uploadFile = ({ patient_id, filename, mime, data, record_id }) =>
    apiClient.post('/clinical-files', { patient_id, filename, mime, data, record_id }).then((r) => r.data);

export const downloadFile = (fileId) =>
    apiClient.get(`/clinical-files/${fileId}`).then((r) => r.data);

export const deleteFile = (fileId) =>
    apiClient.delete(`/clinical-files/${fileId}`).then((r) => r.data);
