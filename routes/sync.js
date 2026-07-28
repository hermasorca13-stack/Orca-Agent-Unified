const express = require('express');
const router = express.Router();

const { authenticate } = require('../middleware/auth');
const { validateRequest, syncSchema } = require('../middleware/validation');
const githubUtils = require('../utils/github');
const manusUtils = require('../utils/manus');
const User = require('../models/User');
const SyncLog = require('../models/SyncLog');

// ============ SYNC DATA FROM GITHUB TO MANUS ============
router.post(
  '/manual',
  authenticate,
  validateRequest(syncSchema),
  async (req, res) => {
    const { repositories, issues, pullRequests, force } = req.body;

    try {
      // Fetch user from database
      const user = await User.findById(req.user.userId).select('+githubToken');
      if (!user) {
        return res.status(404).json({ error: 'User not found' });
      }

      // Check if already syncing (unless force flag)
      const lastSync = await SyncLog.findOne(
        { userId: user._id, status: 'in_progress' }
      );
      if (lastSync && !force) {
        return res.status(409).json({ 
          error: 'Sync already in progress',
          lastSyncAt: lastSync.startTime
        });
      }

      // Create sync log
      const syncLog = new SyncLog({
        userId: user._id,
        syncType: 'manual',
        status: 'in_progress',
        startTime: new Date()
      });
      await syncLog.save();

      // Fetch data from GitHub
      const data = {};
      let recordsProcessed = 0;

      if (repositories) {
        data.repositories = await githubUtils.fetchRepositories(user.githubToken);
        recordsProcessed += data.repositories.length;
      }

      if (issues) {
        data.issues = await githubUtils.fetchIssues(user.githubToken);
        recordsProcessed += data.issues.length;
      }

      if (pullRequests) {
        data.pullRequests = await githubUtils.fetchPullRequests(user.githubToken);
        recordsProcessed += data.pullRequests.length;
      }

      // Send to Manus
      const manusResponse = await manusUtils.syncDataToManus(user.manusId, data);

      // Update sync log
      syncLog.status = 'completed';
      syncLog.endTime = new Date();
      syncLog.recordsProcessed = recordsProcessed;
      syncLog.recordsSuccessful = manusResponse.recordsProcessed || recordsProcessed;
      await syncLog.save();

      // Update user
      user.lastSyncAt = new Date();
      await user.save();

      res.json({
        success: true,
        message: 'Sync completed successfully',
        syncLog: {
          id: syncLog._id,
          duration: syncLog.endTime - syncLog.startTime,
          recordsProcessed: syncLog.recordsProcessed,
          recordsSuccessful: syncLog.recordsSuccessful
        },
        data: {
          repositoriesCount: data.repositories?.length || 0,
          issuesCount: data.issues?.length || 0,
          pullRequestsCount: data.pullRequests?.length || 0
        }
      });

    } catch (error) {
      console.error('Sync error:', error);

      // Update sync log with error
      const syncLog = await SyncLog.findOne(
        { userId: req.user.userId, status: 'in_progress' }
      );
      if (syncLog) {
        syncLog.status = 'failed';
        syncLog.error = error.message;
        syncLog.endTime = new Date();
        await syncLog.save();
      }

      res.status(500).json({
        error: 'Sync failed',
        message: error.message
      });
    }
  }
);

// ============ GET SYNC HISTORY ============
router.get('/history', authenticate, async (req, res) => {
  try {
    const { limit = 10, page = 1 } = req.query;
    const skip = (page - 1) * limit;

    const syncLogs = await SyncLog
      .find({ userId: req.user.userId })
      .sort({ createdAt: -1 })
      .limit(parseInt(limit))
      .skip(skip);

    const total = await SyncLog.countDocuments({ userId: req.user.userId });

    res.json({
      data: syncLogs,
      pagination: {
        total,
        page: parseInt(page),
        limit: parseInt(limit),
        pages: Math.ceil(total / limit)
      }
    });

  } catch (error) {
    console.error('Error fetching sync history:', error);
    res.status(500).json({ error: error.message });
  }
});

// ============ GET LATEST SYNC STATUS ============
router.get('/status', authenticate, async (req, res) => {
  try {
    const latestSync = await SyncLog
      .findOne({ userId: req.user.userId })
      .sort({ createdAt: -1 });

    if (!latestSync) {
      return res.json({ status: 'never', lastSync: null });
    }

    res.json({
      status: latestSync.status,
      lastSync: latestSync.endTime || latestSync.startTime,
      duration: latestSync.endTime ? latestSync.endTime - latestSync.startTime : null,
      recordsProcessed: latestSync.recordsProcessed,
      recordsSuccessful: latestSync.recordsSuccessful
    });

  } catch (error) {
    console.error('Error fetching sync status:', error);
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;
