const mongoose = require('mongoose');
const bcryptjs = require('bcryptjs');

const UserSchema = new mongoose.Schema(
  {
    githubId: {
      type: Number,
      required: true,
      unique: true,
      index: true
    },
    githubLogin: {
      type: String,
      required: true,
      unique: true
    },
    githubToken: {
      type: String,
      required: true,
      select: false // Don't return by default
    },
    manusId: {
      type: String,
      unique: true,
      sparse: true
    },
    manusToken: {
      type: String,
      select: false
    },
    email: {
      type: String,
      lowercase: true,
      match: [/^\S+@\S+\.\S+$/, 'Please provide a valid email']
    },
    profile: {
      name: String,
      avatar: String,
      bio: String,
      company: String,
      location: String,
      blog: String,
      publicRepos: Number
    },
    linkedAt: {
      type: Date,
      default: Date.now
    },
    lastSyncAt: Date,
    syncSettings: {
      autoSync: {
        type: Boolean,
        default: false
      },
      syncRepos: {
        type: Boolean,
        default: true
      },
      syncIssues: {
        type: Boolean,
        default: true
      },
      syncPRs: {
        type: Boolean,
        default: true
      }
    },
    isActive: {
      type: Boolean,
      default: true
    }
  },
  { timestamps: true }
);

// Hash sensitive tokens before saving (optional)
UserSchema.pre('save', async function (next) {
  if (!this.isModified('manusToken')) return next();
  try {
    const salt = await bcryptjs.genSalt(Number(process.env.BCRYPT_ROUNDS) || 10);
    this.manusToken = await bcryptjs.hash(this.manusToken, salt);
    next();
  } catch (error) {
    next(error);
  }
});

module.exports = mongoose.model('User', UserSchema);
