/**
 * routes/chat.js
 * ───────────────
 * Proxy routes to the Python AI service.
 *
 * POST /          — non-streaming completions proxy
 * POST /stream    — SSE streaming proxy (pipes Python SSE → client)
 */

const express = require('express');
const axios = require('axios');
const crypto = require('crypto');
const verifyToken = require('../middleware/authMiddleware');

const router = express.Router();

const PROXY_TIMEOUT_MS = 30000;

// ── POST / — non-streaming completions ───────────────────────────────────────

router.post('/', verifyToken, async (req, res) => {
  try {
    const pythonUrl = process.env.PYTHON_API_URL;
    const apiKey = process.env.PYTHON_API_KEY;

    const body = {
      request_id: req.body.request_id || crypto.randomUUID(),
      ...req.body,
    };

    const response = await axios.post(pythonUrl, body, {
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': req.user.id,
        'X-API-Key': apiKey,
      },
      timeout: PROXY_TIMEOUT_MS,
    });

    return res.status(200).json(response.data);
  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    console.error('Proxy error:', err.message);
    return res.status(502).json({ message: 'Python service unavailable.', error: err.message });
  }
});

// ── POST /stream — SSE streaming proxy ───────────────────────────────────────

router.post('/stream', verifyToken, async (req, res) => {
  try {
    const pythonStreamUrl = process.env.PYTHON_STREAM_URL ||
      (process.env.PYTHON_API_URL || '').replace('/completions', '/stream');
    const apiKey = process.env.PYTHON_API_KEY;

    const body = {
      request_id: req.body.request_id || crypto.randomUUID(),
      ...req.body,
    };

    // Make the upstream call FIRST — don't flush SSE headers until we know it succeeded
    const upstream = await axios.post(pythonStreamUrl, body, {
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': req.user.id,
        'X-API-Key': apiKey,
      },
      responseType: 'stream',
      timeout: PROXY_TIMEOUT_MS,
    });

    // Upstream connected — now set SSE headers and start streaming
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('X-Accel-Buffering', 'no');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders();

    upstream.data.on('data', (chunk) => {
      res.write(chunk);
    });

    upstream.data.on('end', () => {
      res.end();
    });

    upstream.data.on('error', (err) => {
      console.error('SSE upstream error:', err.message);
      res.end();
    });

    req.on('close', () => {
      if (upstream.data.destroy) upstream.data.destroy();
    });

  } catch (err) {
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    console.error('SSE proxy error:', err.message);
    return res.status(502).json({ message: 'Python SSE service unavailable.', error: err.message });
  }
});

module.exports = router;
