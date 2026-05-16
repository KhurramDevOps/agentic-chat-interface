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
const proxyRoutes = require('./routes/proxy');

const app = express();

// ── Security & logging middleware ─────────────────────────────────────────────

app.use(helmet());
app.use(cors());

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

// ── Start (only when run directly) ───────────────────────────────────────────

if (require.main === module) {
  const PORT = process.env.PORT || 5000;

  connectDB()
    .then(() => {
      const server = app.listen(PORT, () => {
        console.log(`Gateway running on port ${PORT}`);
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
