/**
 * models/User.js
 * ───────────────
 * Mongoose schema and model for application users.
 */

const mongoose = require('mongoose');

const userSchema = new mongoose.Schema(
  {
    name: {
      type: String,
      required: [true, 'Name is required'],
      trim: true,
    },
    email: {
      type: String,
      required: [true, 'Email is required'],
      unique: true,
      lowercase: true,
      trim: true,
    },
    password: {
      type: String,
      required: [true, 'Password is required'],
    },
    resetToken: {
      type: String,
      default: null,
    },
    resetTokenExpiry: {
      type: Date,
      default: null,
    },
    refreshToken: {
      type: String,
      default: null,
    },
    memory: {
      name: {
        type: String,
        default: '',
        trim: true,
      },
      nickname: {
        type: String,
        default: '',
        trim: true,
      },
      occupation: {
        type: String,
        default: '',
        trim: true,
      },
      location: {
        type: String,
        default: '',
        trim: true,
      },
      facts: {
        type: [String],
        default: [],
      },
      lastUpdated: {
        type: Date,
        default: null,
      },
    },
    onboarding: {
      completed: {
        type: Boolean,
        default: false,
      },
      interests: {
        type: [String],
        default: [],
      },
      responseStyle: {
        type: String,
        enum: ['concise', 'detailed', 'casual', 'formal', ''],
        default: '',
      },
      memoryEnabled: {
        type: Boolean,
        default: true,
      },
      webSearchEnabled: {
        type: Boolean,
        default: true,
      },
      completedAt: {
        type: Date,
        default: null,
      },
    },
    onboardingComplete: {
      type: Boolean,
      default: false,
      index: true,
    },
  },
  { timestamps: true }
);

module.exports = mongoose.model('User', userSchema);
