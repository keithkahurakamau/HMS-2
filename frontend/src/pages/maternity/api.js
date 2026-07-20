import { apiClient } from '../../api/client';

// apiClient's baseURL is already '/api' (see src/api/client.js), so paths
// here omit the leading /api segment that the backend routers declare.
export const listEpisodes = (params = {}) =>
  apiClient.get('/maternity/episodes', { params }).then((r) => r.data);
export const createEpisode = (payload) =>
  apiClient.post('/maternity/episodes', payload).then((r) => r.data);
export const getEpisode = (episodeId) =>
  apiClient.get(`/maternity/episodes/${episodeId}`).then((r) => r.data);
export const closeEpisode = (episodeId, payload) =>
  apiClient.patch(`/maternity/episodes/${episodeId}/close`, payload).then((r) => r.data);
export const createAncVisit = (episodeId, payload) =>
  apiClient.post(`/maternity/episodes/${episodeId}/anc-visits`, payload).then((r) => r.data);
export const createPncVisit = (episodeId, payload) =>
  apiClient.post(`/maternity/episodes/${episodeId}/pnc-visits`, payload).then((r) => r.data);
export const linkLabor = (episodeId, payload) =>
  apiClient.post(`/maternity/episodes/${episodeId}/labor`, payload).then((r) => r.data);
export const appendPartograph = (laborId, payload) =>
  apiClient.post(`/maternity/labor/${laborId}/partograph`, payload).then((r) => r.data);
export const getPartograph = (laborId) =>
  apiClient.get(`/maternity/labor/${laborId}/partograph`).then((r) => r.data);
export const recordDelivery = (episodeId, payload) =>
  apiClient.post(`/maternity/episodes/${episodeId}/delivery`, payload).then((r) => r.data);
export const registerNewborn = (newbornId) =>
  apiClient.post(`/maternity/newborns/${newbornId}/register-patient`).then((r) => r.data);
export const getLaborBoard = () =>
  apiClient.get('/maternity/board').then((r) => r.data);
export const getMaternityQueue = () =>
  apiClient.get('/queue/', { params: { department: 'Maternity' } }).then((r) => r.data);
