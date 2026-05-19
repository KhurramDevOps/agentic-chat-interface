/**
 * routes/proxy.js
 * ────────────────
 * Proxy routes for history and usage endpoints.
 *
 * GET    /history/:sessionId  — fetch conversation history from Python service
 * DELETE /history/:sessionId  — clear conversation history
 * GET    /usage               — fetch token usage for the authenticated user
 *
 * All routes inject X-User-ID, X-API-Key, and X-Request-ID into upstream headers.
 */

const express = require('express');
const axios = require('axios');
const crypto = require('crypto');
const verifyToken = require('../middleware/authMiddleware');

const router = express.Router();

const PROXY_TIMEOUT_MS = 30000;

// ── Shared header builder ─────────────────────────────────────────────────────

function buildHeaders(req) {
  return {
    'Content-Type': 'application/json',
    'X-User-ID': req.user.id,
    'X-API-Key': process.env.PYTHON_API_KEY,
    'X-Request-ID': req.headers['x-request-id'] || crypto.randomUUID(),
  };
}

function pythonBase() {
  return (
    process.env.PYTHON_BASE_URL ||
    (process.env.PYTHON_API_URL || 'http://localhost:8000/api/v1').replace(
      /\/chat\/completions$/,
      ''
    )
  );
}

// ── GET /history/:sessionId ───────────────────────────────────────────────────

router.get('/history/:sessionId', verifyToken, async (req, res) => {
  try {
    const url = `${pythonBase()}/chat/history/${req.params.sessionId}`;
    const response = await axios.get(url, {
      headers: buildHeaders(req),
      timeout: PROXY_TIMEOUT_MS,
    });
    return res.status(200).json(response.data);
  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    return res.status(502).json({ message: 'Python service unavailable.', error: err.message });
  }
});

// ── DELETE /history/:sessionId ────────────────────────────────────────────────

router.delete('/history/:sessionId', verifyToken, async (req, res) => {
  try {
    const url = `${pythonBase()}/chat/history/${req.params.sessionId}`;
    const response = await axios.delete(url, {
      headers: buildHeaders(req),
      timeout: PROXY_TIMEOUT_MS,
    });
    return res.status(response.status || 200).json(response.data || {});
  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    return res.status(502).json({ message: 'Python service unavailable.', error: err.message });
  }
});

// ── GET /usage ────────────────────────────────────────────────────────────────

router.get('/usage', verifyToken, async (req, res) => {
  try {
    const url = `${pythonBase()}/users/${req.user.id}/usage`;
    const response = await axios.get(url, {
      headers: buildHeaders(req),
      timeout: PROXY_TIMEOUT_MS,
    });
    return res.status(200).json(response.data);
  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    return res.status(502).json({ message: 'Python service unavailable.', error: err.message });
  }
});

module.exports = router;
