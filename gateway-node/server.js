/**
 * server.js
 * ──────────
 * Express application entry point.
 *
 * Exports `app` for Jest. Only calls connectDB() + listen() when run directly.
 *
 * Proxy responsibilities:
 *   - /api/v1/stream/ws/*  → WebSocket proxy → Python FastAPI (port 8000)
 *   - HTTP history/usage   → handled by routes/proxy.js via Axios
 */

require('dotenv').config();

const http = require('http');
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const jwt = require('jsonwebtoken');
const { createProxyMiddleware } = require('http-proxy-middleware');

const connectDB = require('./db');
const authRoutes = require('./routes/auth');
const chatRoutes = require('./routes/chat');
const proxyRoutes = require('./routes/proxy');

const app = express();

// ── Security & logging middleware ─────────────────────────────────────────────

app.use(helmet());

const allowedOrigins = process.env.FRONTEND_URL
  ? [process.env.FRONTEND_URL]
  : ['http://localhost:3000'];

app.use(cors({
  origin: (origin, callback) => {
    if (!origin || allowedOrigins.includes(origin)) {
      callback(null, true);
    } else {
      callback(new Error(`CORS: origin ${origin} not allowed`));
    }
  },
  credentials: true,
}));

if (process.env.NODE_ENV !== 'test') {
  app.use(morgan('dev'));
}

app.use(express.json());

// ── Health check ──────────────────────────────────────────────────────────────

app.get('/api/health', (req, res) => {
  res.status(200).json({
    status: 'healthy',
    service: 'gateway-node',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  });
});

// ── Routes ────────────────────────────────────────────────────────────────────

app.use('/api/auth', authRoutes);
app.use('/api/chat', chatRoutes);
app.use('/api', proxyRoutes);   // mounts /api/history/:id and /api/usage

// ── Python WebSocket proxy ────────────────────────────────────────────────────
// Forwards  ws://gateway:5001/api/v1/stream/ws/:id
//        →  ws://python:8000/api/v1/stream/ws/:id
//
// JWT is verified from the Authorization header or ?token= query param
// BEFORE the upgrade is forwarded to Python.

const PYTHON_BASE = process.env.PYTHON_BASE_URL || 'http://127.0.0.1:8000';

const wsProxy = createProxyMiddleware({
  target: PYTHON_BASE,
  changeOrigin: true,
  ws: true,
  // Inject the API key so Python can authenticate the gateway
  on: {
    proxyReqWs: (proxyReq, req, socket, options, head) => {
      proxyReq.setHeader('X-API-Key', process.env.PYTHON_API_KEY || '');
      if (req.user) {
        proxyReq.setHeader('X-User-ID', req.user.id || '');
        proxyReq.setHeader('X-User-Email', req.user.email || '');
      }
    },
    error: (err, req, res) => {
      console.error('[WS Proxy] error:', err.message);
      if (res && res.end) res.end();
    },
  },
});

// Mount the WS proxy on the HTTP app so http-proxy-middleware can intercept
// the upgrade event via the server reference set below.
app.use('/api/v1/stream', wsProxy);

// ── Start (only when run directly) ───────────────────────────────────────────

if (require.main === module) {
  const PORT = process.env.PORT || 5001;

  connectDB()
    .then(() => {
      // Use http.createServer so we can attach the 'upgrade' handler for WS
      const server = http.createServer(app);

      // ── WebSocket upgrade — verify JWT then proxy ───────────────────────
      server.on('upgrade', (req, socket, head) => {
        const url = req.url || '';

        // Only proxy WebSocket connections to the stream path
        if (!url.startsWith('/api/v1/stream/ws/')) {
          socket.destroy();
          return;
        }

        // Extract JWT from Authorization header or ?token= query param
        let token = null;
        const authHeader = req.headers['authorization'] || '';
        if (authHeader.startsWith('Bearer ')) {
          token = authHeader.slice(7).trim();
        } else {
          // Fallback: ?token=<jwt> in query string
          const qs = url.includes('?') ? url.split('?')[1] : '';
          const params = new URLSearchParams(qs);
          token = params.get('token');
        }

        if (!token) {
          console.warn('[WS] Rejected — no token provided for', url);
          socket.write('HTTP/1.1 401 Unauthorized\r\n\r\n');
          socket.destroy();
          return;
        }

        try {
          const decoded = jwt.verify(token, process.env.JWT_SECRET);
          if (!decoded || !decoded.id) {
            throw new Error('invalid token payload');
          }
          req.user = decoded;
        } catch (err) {
          console.warn('[WS] Rejected — invalid token:', err.message);
          socket.write('HTTP/1.1 401 Unauthorized\r\n\r\n');
          socket.destroy();
          return;
        }

        // Token valid — forward the upgrade to Python
        wsProxy.upgrade(req, socket, head);
      });

      server.listen(PORT, () => {
        console.log(`Gateway running on port ${PORT}`);
      });

      // ── Graceful shutdown ─────────────────────────────────────────────────
      const shutdown = async (signal) => {
        console.log(`\n${signal} received — shutting down gracefully...`);
        server.close(async () => {
          try {
            const mongoose = require('mongoose');
            await mongoose.disconnect();
            console.log('MongoDB connection closed.');
          } catch (err) {
            console.error('Error closing MongoDB:', err.message);
          }
          process.exit(0);
        });

        setTimeout(() => {
          console.error('Forced shutdown after timeout.');
          process.exit(1);
        }, 10000);
      };

      process.on('SIGTERM', () => shutdown('SIGTERM'));
      process.on('SIGINT', () => shutdown('SIGINT'));
    })
    .catch((err) => {
      console.error('Failed to connect to MongoDB:', err.message);
      process.exit(1);
    });
}

module.exports = app;
