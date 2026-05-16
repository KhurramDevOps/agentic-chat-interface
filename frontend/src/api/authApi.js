import apiClient from './apiClient';

/**
 * authApi.js
 * ───────────
 * Auth REST calls through the pre-configured Axios instance.
 * Token attachment and refresh are handled by apiClient interceptors.
 */

export const login = (email, password) =>
  apiClient.post('/api/auth/login', { email, password });

export const signup = (name, email, password) =>
  apiClient.post('/api/auth/signup', { name, email, password });

export const logout = () =>
  apiClient.post('/api/auth/logout');

export const fetchMe = () =>
  apiClient.get('/api/auth/me');

export const refresh = (refreshToken) =>
  apiClient.post('/api/auth/refresh', { refreshToken });
