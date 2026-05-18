const mongoose = require('mongoose');

const longTermMemorySchema = new mongoose.Schema({
  userId: { type: String, required: true, index: true },
  content: { type: String, required: true },
  importance: { type: Number, min: 1, max: 10, default: 7 },
  sourceSessionId: { type: String },
  tags: [{ type: String }],
  lastAccessedAt: { type: Date, default: Date.now },
}, { timestamps: true });

longTermMemorySchema.index({ userId: 1, importance: -1 });

module.exports = mongoose.model('LongTermMemory', longTermMemorySchema);
