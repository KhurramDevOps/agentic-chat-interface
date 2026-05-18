import api from './axiosInstance';

export const loginApi = (credentials) =>
  api.post('/api/auth/login', credentials).then((response) => response.data);

export const registerApi = (userData) =>
  api.post('/api/auth/register', userData).then((response) => response.data);

export const logoutApi = () =>
  api.post('/api/auth/logout').then((response) => response.data);

export const refreshTokenApi = () =>
  api.post('/api/auth/refresh').then((response) => response.data);
