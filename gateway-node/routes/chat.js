/**
 * routes/chat.js
 * ───────────────
 * Proxy route — forwards authenticated chat requests to the Python AI service.
 *
 * POST /
 *   - Protected by verifyToken middleware
 *   - Forwards req.body to PYTHON_API_URL
 *   - Injects X-User-ID and X-API-Key headers
 *   - Returns the Python service response to the client
 */

const express = require('express');
const axios = require('axios');
const crypto = require('crypto');
const verifyToken = require('../middleware/authMiddleware');

const router = express.Router();

router.post('/', verifyToken, async (req, res) => {
  try {
    const pythonUrl = process.env.PYTHON_API_URL;
    const apiKey = process.env.PYTHON_API_KEY;

    // Build the forwarded body — inject a request_id if not provided
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
    });

    return res.status(200).json(response.data);
  } catch (err) {
    // Propagate upstream HTTP errors with their original status
    if (err.response) {
      return res.status(err.response.status).json(err.response.data);
    }
    // Network / connection errors
    console.error('Proxy error:', err.message);
    return res.status(502).json({ message: 'Python service unavailable.', error: err.message });
  }
});

module.exports = router;
