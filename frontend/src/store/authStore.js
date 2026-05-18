import { create } from 'zustand';
import axios from 'axios';

/**
 * authStore.js
 * ─────────────
 * Zustand store for authentication state.
 *
 * Access token: in-memory only (never persisted — XSS safe).
 * Refresh token: localStorage (survives page refresh).
 */

const GATEWAY = process.env.REACT_APP_GATEWAY_URL || 'http://localhost:3001';

const useAuthStore = create((set, get) => ({
  user: null,
  token: null,
  isLoading: false,
  error: null,

  // ── Login ───────────────────────────────────────────────────────────────

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const { data } = await axios.post(`${GATEWAY}/api/auth/login`, { email, password });
      localStorage.setItem('refreshToken', data.refreshToken);
      set({ token: data.token, isLoading: false });
      await get().fetchMe();
      return true;
    } catch (err) {
      const message =
        err?.response?.data?.message ||
        (err?.code === 'ERR_NETWORK' ? 'Cannot reach the server. Is the gateway running on port 5001?' : null) ||
        err?.message ||
        'Login failed.';
      set({ error: message, isLoading: false });
      return false;
    }
  },

  // ── Signup ──────────────────────────────────────────────────────────────

  signup: async (name, email, password) => {
    set({ isLoading: true, error: null });
    try {
      await axios.post(`${GATEWAY}/api/auth/signup`, { name, email, password });
      return await get().login(email, password);
    } catch (err) {
      const message =
        err?.response?.data?.message ||
        (err?.code === 'ERR_NETWORK' ? 'Cannot reach the server. Is the gateway running on port 5001?' : null) ||
        err?.message ||
        'Registration failed.';
      set({ error: message, isLoading: false });
      return false;
    }
  },

  // ── Logout ──────────────────────────────────────────────────────────────

  logout: async () => {
    try {
      const { token } = get();
      if (token) {
        await axios.post(
          `${GATEWAY}/api/auth/logout`,
          {},
          { headers: { Authorization: `Bearer ${token}` } }
        );
      }
    } catch (_) {
      // Ignore logout errors — clear state regardless
    } finally {
      localStorage.removeItem('refreshToken');
      set({ user: null, token: null, error: null });
    }
  },

  // ── Silent token refresh ────────────────────────────────────────────────

  refreshAccessToken: async () => {
    const refreshToken = localStorage.getItem('refreshToken');
    if (!refreshToken) throw new Error('No refresh token available.');

    const { data } = await axios.post(`${GATEWAY}/api/auth/refresh`, { refreshToken });
    set({ token: data.token });
    return data.token;
  },

  // ── Fetch current user ──────────────────────────────────────────────────

  fetchMe: async () => {
    try {
      const { token } = get();
      if (!token) return;
      const { data } = await axios.get(`${GATEWAY}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      set({ user: data });
    } catch (_) {
      // Non-critical — user profile fetch failure doesn't break the app
    }
  },

  clearError: () => set({ error: null }),
}));

export default useAuthStore;
