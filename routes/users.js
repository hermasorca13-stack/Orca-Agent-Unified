const express = require('express');
const router = express.Router();

const { authenticate } = require('../middleware/auth');
const User = require('../models/User');

// ============ GET CURRENT USER PROFILE ============
router.get('/me', authenticate, async (req, res) => {
  try {
    const user = await User.findById(req.user.userId).select('-githubToken -manusToken');

    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    res.json({
      user: {
        id: user._id,
        githubLogin: user.githubLogin,
        githubId: user.githubId,
        manusId: user.manusId,
        email: user.email,
        profile: user.profile,
        linkedAt: user.linkedAt,
        lastSyncAt: user.lastSyncAt,
        syncSettings: user.syncSettings,
        isActive: user.isActive
      }
    });

  } catch (error) {
    console.error('Error fetching user profile:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============ UPDATE SYNC SETTINGS ============
router.patch('/sync-settings', authenticate, async (req, res) => {
  try {
    const user = await User.findById(req.user.userId);

    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Update settings
    if (req.body.autoSync !== undefined) {
      user.syncSettings.autoSync = req.body.autoSync;
    }
    if (req.body.syncRepos !== undefined) {
      user.syncSettings.syncRepos = req.body.syncRepos;
    }
    if (req.body.syncIssues !== undefined) {
      user.syncSettings.syncIssues = req.body.syncIssues;
    }
    if (req.body.syncPRs !== undefined) {
      user.syncSettings.syncPRs = req.body.syncPRs;
    }

    await user.save();

    res.json({
      message: 'Sync settings updated',
      syncSettings: user.syncSettings
    });

  } catch (error) {
    console.error('Error updating sync settings:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============ DEACTIVATE ACCOUNT ============
router.post('/deactivate', authenticate, async (req, res) => {
  try {
    const user = await User.findById(req.user.userId);

    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    user.isActive = false;
    await user.save();

    res.json({ message: 'Account deactivated' });

  } catch (error) {
    console.error('Error deactivating account:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============ DELETE ACCOUNT ============
router.delete('/me', authenticate, async (req, res) => {
  try {
    const user = await User.findByIdAndDelete(req.user.userId);

    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    res.json({ message: 'Account deleted successfully' });

  } catch (error) {
    console.error('Error deleting account:', error);
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;
