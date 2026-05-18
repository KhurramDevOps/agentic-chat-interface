import api from './axiosInstance';

export const sendMessageApi = ({ message, session_id }) =>
  api.post('/api/chat/message', { message, session_id }).then((response) => response.data);

export const getSessionsApi = () =>
  api.get('/api/chat/sessions').then((response) => response.data);

export const getHistoryApi = (sessionId) =>
  api.get(`/api/chat/history/${sessionId}`).then((response) => response.data);

export const deleteSessionApi = (sessionId) =>
  api.delete(`/api/chat/history/${sessionId}`).then((response) => response.data);
