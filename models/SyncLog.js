const mongoose = require('mongoose');

const SyncLogSchema = new mongoose.Schema(
  {
    userId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: true
    },
    syncType: {
      type: String,
      enum: ['manual', 'automatic', 'webhook'],
      default: 'manual'
    },
    dataType: {
      type: String,
      enum: ['repositories', 'issues', 'pullRequests', 'all'],
      default: 'all'
    },
    status: {
      type: String,
      enum: ['pending', 'in_progress', 'completed', 'failed'],
      default: 'pending'
    },
    recordsProcessed: {
      type: Number,
      default: 0
    },
    recordsSuccessful: {
      type: Number,
      default: 0
    },
    recordsFailed: {
      type: Number,
      default: 0
    },
    error: String,
    details: mongoose.Schema.Types.Mixed,
    startTime: Date,
    endTime: Date
  },
  { timestamps: true }
);

// Virtual for duration
SyncLogSchema.virtual('duration').get(function () {
  if (this.startTime && this.endTime) {
    return this.endTime - this.startTime;
  }
  return null;
});

module.exports = mongoose.model('SyncLog', SyncLogSchema);
