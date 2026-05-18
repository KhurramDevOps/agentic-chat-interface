/**
 * routes/proxy.js
 * ────────────────
 * HTTP proxy routes for history and usage endpoints.
 *
 * GET    /api/history/:sessionId  → Python /api/v1/chat/history/:sessionId
 * DELETE /api/history/:sessionId  → Python /api/v1/chat/history/:sessionId
 * GET    /api/usage               → Python /api/v1/users/:userId/usage
 *
 * All routes require a valid JWT and inject X-User-ID + X-API-Key upstream.
 */

const express = require('express');
const axios = require('axios');
const crypto = require('crypto');
const verifyToken = require('../middleware/authMiddleware');

const router = express.Router();

const PROXY_TIMEOUT_MS = 30000;

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildHeaders(req) {
  return {
    'Content-Type': 'application/json',
    'X-User-ID': req.user.id,
    'X-API-Key': process.env.PYTHON_API_KEY || '',
    'X-Request-ID': req.headers['x-request-id'] || crypto.randomUUID(),
  };
}

/**
 * Returns the Python service base URL.
 * Strips any trailing path so we can append clean routes.
 * e.g. "http://127.0.0.1:8000/api/v1/chat/completions" → "http://127.0.0.1:8000"
 */
function pythonOrigin() {
  const base = process.env.PYTHON_BASE_URL || 'http://127.0.0.1:8000';
  // Strip everything after the host:port
  try {
    const u = new URL(base);
    return `${u.protocol}//${u.host}`;
  } catch {
    return base.replace(/\/api.*$/, '');
  }
}

// ── GET /history/:sessionId ───────────────────────────────────────────────────

router.get('/history/:sessionId', verifyToken, async (req, res) => {
  try {
    // Python endpoint: GET /api/v1/chat/history/:sessionId
    const url = `${pythonOrigin()}/api/v1/chat/history/${req.params.sessionId}`;
    const response = await axios.get(url, {
      headers: buildHeaders(req),
      timeout: PROXY_TIMEOUT_MS,
    });
    return res.status(200).json(response.data);
  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    console.error('[proxy] GET history error:', err.message);
    return res.status(502).json({ message: 'Python service unavailable.', error: err.message });
  }
});

// ── DELETE /history/:sessionId ────────────────────────────────────────────────

router.delete('/history/:sessionId', verifyToken, async (req, res) => {
  try {
    const url = `${pythonOrigin()}/api/v1/chat/history/${req.params.sessionId}`;
    const response = await axios.delete(url, {
      headers: buildHeaders(req),
      timeout: PROXY_TIMEOUT_MS,
    });
    return res.status(response.status || 200).json(response.data || {});
  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    console.error('[proxy] DELETE history error:', err.message);
    return res.status(502).json({ message: 'Python service unavailable.', error: err.message });
  }
});

// ── GET /usage ────────────────────────────────────────────────────────────────

router.get('/usage', verifyToken, async (req, res) => {
  try {
    const url = `${pythonOrigin()}/api/v1/users/${req.user.id}/usage`;
    const response = await axios.get(url, {
      headers: buildHeaders(req),
      timeout: PROXY_TIMEOUT_MS,
    });
    return res.status(200).json(response.data);
  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    console.error('[proxy] GET usage error:', err.message);
    return res.status(502).json({ message: 'Python service unavailable.', error: err.message });
  }
});

module.exports = router;
