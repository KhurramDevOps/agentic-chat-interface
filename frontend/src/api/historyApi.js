import apiClient from './apiClient';

/**
 * historyApi.js
 * ──────────────
 * Conversation history and token usage endpoints.
 * All calls go through apiClient which attaches the JWT automatically.
 */

/**
 * Fetch conversation history for a session.
 * GET /api/history/:sessionId
 * Returns: { session_id, messages: [{ role, content, timestamp }] }
 */
export const getHistory = (sessionId) =>
  apiClient.get(`/api/history/${sessionId}`);

/**
 * Delete all history for a session.
 * DELETE /api/history/:sessionId
 */
export const deleteHistory = (sessionId) =>
  apiClient.delete(`/api/history/${sessionId}`);

/**
 * Fetch token usage stats for the authenticated user.
 * GET /api/usage
 * Returns: { user_id, total_tokens, requests }
 */
export const getUsage = () =>
  apiClient.get('/api/usage');
