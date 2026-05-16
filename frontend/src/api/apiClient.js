import axios from 'axios';

/**
 * apiClient.js
 * ─────────────
 * Pre-configured Axios instance.
 * Request interceptor attaches the in-memory access token.
 * Response interceptor handles 401 → silent token refresh → retry.
 *
 * NOTE: authStore is imported lazily inside the interceptor to avoid
 * circular dependency issues at module load time.
 */

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_GATEWAY_URL || 'http://localhost:3001',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Request interceptor — attach access token ─────────────────────────────

apiClient.interceptors.request.use(
  (config) => {
    // Lazy import to avoid circular dependency
    const { default: useAuthStore } = require('./authStoreRef');
    const token = useAuthStore.getState().token;
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ── Response interceptor — handle 401 with silent refresh ─────────────────

let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then((token) => {
            originalRequest.headers['Authorization'] = `Bearer ${token}`;
            return apiClient(originalRequest);
          })
          .catch((err) => Promise.reject(err));
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const { default: useAuthStore } = require('./authStoreRef');
        const newToken = await useAuthStore.getState().refreshAccessToken();
        processQueue(null, newToken);
        originalRequest.headers['Authorization'] = `Bearer ${newToken}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        const { default: useAuthStore } = require('./authStoreRef');
        useAuthStore.getState().logout();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
