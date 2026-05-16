/**
 * db.js
 * ──────
 * Mongoose connection helper.
 * Call connectDB() once at app startup.
 */

const mongoose = require('mongoose');

const connectDB = async () => {
  const uri = process.env.MONGO_URI || 'mongodb://localhost:27017/gateway';
  await mongoose.connect(uri);
  console.log('MongoDB connected:', uri.split('@').pop());
};

module.exports = connectDB;
