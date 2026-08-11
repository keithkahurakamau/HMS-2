import { apiClient } from '../../api/client';

// apiClient baseURL is '/api', so paths omit the leading /api segment.
export const listOrders = (params = {}) =>
  apiClient.get('/dialysis/orders', { params }).then((r) => r.data);
export const createOrder = (payload) =>
  apiClient.post('/dialysis/orders', payload).then((r) => r.data);
export const getOrder = (orderId) =>
  apiClient.get(`/dialysis/orders/${orderId}`).then((r) => r.data);

export const connectOrder = (orderId) =>
  apiClient.post(`/dialysis/orders/${orderId}/connect`).then((r) => r.data);
export const disconnectOrder = (orderId) =>
  apiClient.post(`/dialysis/orders/${orderId}/disconnect`).then((r) => r.data);
export const completeOrder = (orderId) =>
  apiClient.post(`/dialysis/orders/${orderId}/complete`).then((r) => r.data);
export const cancelOrder = (orderId, payload) =>
  apiClient.post(`/dialysis/orders/${orderId}/cancel`, payload).then((r) => r.data);

export const addObservation = (orderId, payload) =>
  apiClient.post(`/dialysis/orders/${orderId}/observations`, payload).then((r) => r.data);
export const addComplication = (orderId, payload) =>
  apiClient.post(`/dialysis/orders/${orderId}/complications`, payload).then((r) => r.data);
export const recordAdequacy = (orderId, payload) =>
  apiClient.post(`/dialysis/orders/${orderId}/adequacy`, payload).then((r) => r.data);
export const addChecklistRun = (orderId, payload) =>
  apiClient.post(`/dialysis/orders/${orderId}/checklist-runs`, payload).then((r) => r.data);

export const listChecklists = () =>
  apiClient.get('/dialysis/checklists').then((r) => r.data);
export const createChecklist = (payload) =>
  apiClient.post('/dialysis/checklists', payload).then((r) => r.data);
export const updateChecklist = (checklistId, payload) =>
  apiClient.put(`/dialysis/checklists/${checklistId}`, payload).then((r) => r.data);

export const getDialysisQueue = () =>
  apiClient.get('/queue/', { params: { department: 'Dialysis' } }).then((r) => r.data);

// ── Phase 2: unit management ────────────────────────────────────────────────
export const listVascularAccesses = (patientId) =>
  apiClient.get('/dialysis/vascular-accesses', { params: patientId ? { patient_id: patientId } : {} }).then((r) => r.data);
export const createVascularAccess = (payload) =>
  apiClient.post('/dialysis/vascular-accesses', payload).then((r) => r.data);
export const updateVascularAccess = (accessId, payload) =>
  apiClient.put(`/dialysis/vascular-accesses/${accessId}`, payload).then((r) => r.data);

export const listMachines = () =>
  apiClient.get('/dialysis/machines').then((r) => r.data);
export const createMachine = (payload) =>
  apiClient.post('/dialysis/machines', payload).then((r) => r.data);
export const updateMachine = (machineId, payload) =>
  apiClient.put(`/dialysis/machines/${machineId}`, payload).then((r) => r.data);

export const listSchedules = (patientId) =>
  apiClient.get('/dialysis/schedules', { params: patientId ? { patient_id: patientId } : {} }).then((r) => r.data);
export const createSchedule = (payload) =>
  apiClient.post('/dialysis/schedules', payload).then((r) => r.data);
export const updateSchedule = (scheduleId, payload) =>
  apiClient.put(`/dialysis/schedules/${scheduleId}`, payload).then((r) => r.data);

export const getRoster = (dateStr) =>
  apiClient.get('/dialysis/roster', { params: dateStr ? { date_str: dateStr } : {} }).then((r) => r.data);
export const getRenalProfile = (patientId) =>
  apiClient.get(`/dialysis/patients/${patientId}/renal-profile`).then((r) => r.data);
export const addConsumable = (orderId, payload) =>
  apiClient.post(`/dialysis/orders/${orderId}/consumables`, payload).then((r) => r.data);
