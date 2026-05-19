const mongoose = require('mongoose');

const messageSchema = new mongoose.Schema(
  {
    role: {
      type: String,
      enum: ['user', 'assistant', 'system'],
      required: true,
    },
    content: {
      type: String,
      required: true,
    },
    memoryUsed: {
      type: Boolean,
      default: false,
    },
    searchUsed: {
      type: Boolean,
      default: false,
    },
    attachments: {
      type: [
        {
          type: {
            type: String,
            enum: ['image', 'document'],
          },
          name: String,
          mimeType: String,
          size: Number,
          url: String,
        },
      ],
      default: [],
    },
    sources: {
      type: [
        {
          title: String,
          url: String,
          snippet: String,
          domain: String,
        },
      ],
      default: [],
    },
    reaction: {
      type: String,
      enum: ['up', 'down', null],
      default: null,
    },
    createdAt: {
      type: Date,
      default: Date.now,
    },
  }
);

const chatSessionSchema = new mongoose.Schema(
  {
    userId: {
      type: String,
      required: true,
      index: true,
    },
    title: {
      type: String,
      required: true,
      trim: true,
      default: 'New Chat',
    },
    messages: {
      type: [messageSchema],
      default: [],
    },
  },
  { timestamps: true }
);

chatSessionSchema.index({ userId: 1, updatedAt: -1 });

module.exports = mongoose.model('ChatSession', chatSessionSchema);
