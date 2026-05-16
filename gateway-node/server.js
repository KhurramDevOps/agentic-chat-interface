/**
 * server.js
 * ──────────
 * Express application entry point.
 *
 * Exports the `app` so Jest can import it without starting a server.
 * Only calls connectDB() and app.listen() when run directly via `node server.js`.
 */

require('dotenv').config();

const express = require('express');
const cors = require('cors');

const connectDB = require('./db');
const authRoutes = require('./routes/auth');
const chatRoutes = require('./routes/chat');

const app = express();

// ── Middleware ────────────────────────────────────────────────────────────────

app.use(cors());
app.use(express.json());

// ── Routes ────────────────────────────────────────────────────────────────────

app.use('/api/auth', authRoutes);
app.use('/api/chat', chatRoutes);

// ── Start (only when run directly, not when required by Jest) ─────────────────

if (require.main === module) {
  const PORT = process.env.PORT || 5000;
  connectDB()
    .then(() => {
      app.listen(PORT, () => {
        console.log(`Gateway running on port ${PORT}`);
      });
    })
    .catch((err) => {
      console.error('Failed to connect to MongoDB:', err.message);
      process.exit(1);
    });
}

module.exports = app;
