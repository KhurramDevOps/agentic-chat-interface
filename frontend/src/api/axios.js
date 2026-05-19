import axios from 'axios';
import config from '../config';

const api = axios.create({ baseURL: `${config.apiUrl}/api` });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('nexus_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default api;
