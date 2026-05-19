/**
 * db.js
 * ──────
 * Mongoose connection helper.
 * Call connectDB() once at app startup.
 */

const mongoose = require('mongoose');

const connectDB = async () => {
  const uri = process.env.MONGODB_URI || process.env.MONGO_URI;

  if (!uri) {
    throw new Error('MONGODB_URI is required for the Node gateway.');
  }

  await mongoose.connect(uri, {
    serverSelectionTimeoutMS: 5000,
    socketTimeoutMS: 45000,
  });
  console.log('MongoDB connected successfully');
};

module.exports = connectDB;
