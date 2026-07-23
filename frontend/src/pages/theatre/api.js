import { apiClient } from '../../api/client';

// apiClient baseURL is '/api', so paths omit the leading /api segment.
export const listCases = (params = {}) =>
  apiClient.get('/theatre/cases', { params }).then((r) => r.data);
export const createCase = (payload) =>
  apiClient.post('/theatre/cases', payload).then((r) => r.data);
export const getCase = (caseId) =>
  apiClient.get(`/theatre/cases/${caseId}`).then((r) => r.data);

export const startCase = (caseId) =>
  apiClient.post(`/theatre/cases/${caseId}/start`).then((r) => r.data);
export const toRecovery = (caseId) =>
  apiClient.post(`/theatre/cases/${caseId}/to-recovery`).then((r) => r.data);
export const completeCase = (caseId) =>
  apiClient.post(`/theatre/cases/${caseId}/complete`).then((r) => r.data);
export const cancelCase = (caseId, payload) =>
  apiClient.post(`/theatre/cases/${caseId}/cancel`, payload).then((r) => r.data);

export const addChecklistRun = (caseId, payload) =>
  apiClient.post(`/theatre/cases/${caseId}/checklist-runs`, payload).then((r) => r.data);
export const putOperativeNote = (caseId, payload) =>
  apiClient.put(`/theatre/cases/${caseId}/operative-note`, payload).then((r) => r.data);
export const putAnaesthesia = (caseId, payload) =>
  apiClient.put(`/theatre/cases/${caseId}/anaesthesia`, payload).then((r) => r.data);

export const listChecklists = (phase) =>
  apiClient.get('/theatre/checklists', { params: phase ? { phase } : {} }).then((r) => r.data);
export const createChecklist = (payload) =>
  apiClient.post('/theatre/checklists', payload).then((r) => r.data);
export const updateChecklist = (checklistId, payload) =>
  apiClient.put(`/theatre/checklists/${checklistId}`, payload).then((r) => r.data);

// ── Phase 2: team, consumables, recovery, board ────────────────────────────
export const addTeamMember = (caseId, payload) =>
  apiClient.post(`/theatre/cases/${caseId}/team-members`, payload).then((r) => r.data);
export const removeTeamMember = (caseId, memberId) =>
  apiClient.delete(`/theatre/cases/${caseId}/team-members/${memberId}`).then((r) => r.data);
export const addConsumable = (caseId, payload) =>
  apiClient.post(`/theatre/cases/${caseId}/consumables`, payload).then((r) => r.data);
export const addRecoveryObs = (caseId, payload) =>
  apiClient.post(`/theatre/cases/${caseId}/recovery-observations`, payload).then((r) => r.data);
export const getBoard = (dateStr) =>
  apiClient.get('/theatre/board', { params: dateStr ? { date_str: dateStr } : {} }).then((r) => r.data);

export const listRooms = () =>
  apiClient.get('/theatre/rooms').then((r) => r.data);
export const createRoom = (payload) =>
  apiClient.post('/theatre/rooms', payload).then((r) => r.data);
export const updateRoom = (roomId, payload) =>
  apiClient.put(`/theatre/rooms/${roomId}`, payload).then((r) => r.data);
