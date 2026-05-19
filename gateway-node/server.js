/**
 * server.js
 * ──────────
 * Express application entry point.
 *
 * Exports `app` for Jest. Only calls connectDB() + listen() when run directly.
 */

require('dotenv').config();

const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');

const connectDB = require('./db');
const authRoutes = require('./routes/auth');
const chatRoutes = require('./routes/chat');
const messagesRoutes = require('./routes/messages');
const proxyRoutes = require('./routes/proxy');
const usersRoutes = require('./routes/users');

const app = express();
const allowedOrigins = process.env.ALLOWED_ORIGINS
  ? process.env.ALLOWED_ORIGINS.split(',').map((origin) => origin.trim()).filter(Boolean)
  : ['http://localhost:3000'];

// ── Security & logging middleware ─────────────────────────────────────────────

app.use(helmet());
app.use(cors({
  origin(origin, callback) {
    if (!origin || allowedOrigins.includes(origin)) {
      callback(null, true);
    } else {
      callback(new Error('Not allowed by CORS'));
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

app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok', service: 'nexus-node-gateway' });
});

// ── Routes ────────────────────────────────────────────────────────────────────

app.use('/api/auth', authRoutes);
app.use('/api/chat', chatRoutes);
app.use('/api/messages', messagesRoutes);
app.use('/api/users', usersRoutes);
app.use('/api', proxyRoutes);   // mounts /api/history/:id and /api/usage

// ── Start (only when run directly) ───────────────────────────────────────────

if (require.main === module) {
  const PORT = process.env.PORT || 5001;

  connectDB()
    .then(() => {
      const server = app.listen(PORT, () => {
        console.log(`Gateway running on port ${PORT}`);
      });

      server.on('error', async (err) => {
        console.error(`Gateway failed to listen on port ${PORT}:`, err.message);
        try {
          const mongoose = require('mongoose');
          await mongoose.disconnect();
        } catch (disconnectErr) {
          console.error('Error closing MongoDB after listen failure:', disconnectErr.message);
        }
        process.exit(1);
      });

      // ── Graceful shutdown ───────────────────────────────────────────────────
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

        // Force exit if graceful shutdown takes too long
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
