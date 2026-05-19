import api from './axiosInstance';

export const sendMessageApi = ({ message, session_id }) =>
  api.post('/chat/message', { message, session_id }).then((response) => response.data);

export const getSessionsApi = () =>
  api.get('/chat/sessions').then((response) => response.data);

export const getHistoryApi = (sessionId) =>
  api.get(`/chat/history/${sessionId}`).then((response) => response.data);

export const deleteSessionApi = (sessionId) =>
  api.delete(`/chat/history/${sessionId}`).then((response) => response.data);
