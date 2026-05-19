import api from './axios';

export const loginApi = (credentials) =>
  api.post('/auth/login', credentials).then((response) => response.data);

export const registerApi = (userData) =>
  api.post('/auth/register', userData).then((response) => response.data);

export const logoutApi = () =>
  api.post('/auth/logout').then((response) => response.data);

export const refreshTokenApi = () =>
  api.post('/auth/refresh').then((response) => response.data);
