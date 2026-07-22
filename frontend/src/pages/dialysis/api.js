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
