const express = require('express');
const crypto = require('crypto');
const router = express.Router();

const manusUtils = require('../utils/manus');
const User = require('../models/User');

// ============ VERIFY GITHUB WEBHOOK SIGNATURE ============
const verifyGitHubSignature = (req, res, next) => {
  const signature = req.headers['x-hub-signature-256'];
  const secret = process.env.GITHUB_WEBHOOK_SECRET;

  if (!signature || !secret) {
    return res.status(400).json({ error: 'Webhook verification failed' });
  }

  const hash = crypto
    .createHmac('sha256', secret)
    .update(JSON.stringify(req.body))
    .digest('hex');

  const expectedSignature = `sha256=${hash}`;

  if (signature !== expectedSignature) {
    return res.status(401).json({ error: 'Invalid signature' });
  }

  next();
};

// ============ GITHUB WEBHOOK RECEIVER ============
router.post('/github', verifyGitHubSignature, async (req, res) => {
  const event = req.headers['x-github-event'];
  const payload = req.body;

  console.log(`📨 Received GitHub webhook: ${event}`);

  try {
    // Find user by repository owner
    const repoOwner = payload.repository?.owner?.login;
    if (!repoOwner) {
      return res.status(400).json({ error: 'Invalid webhook payload' });
    }

    const user = await User.findOne({ githubLogin: repoOwner });
    if (!user) {
      return res.status(404).json({ error: 'User not found' });
    }

    // Handle different event types
    const eventData = {
      eventType: event,
      payload: payload,
      receivedAt: new Date(),
      userId: user._id
    };

    // Send to Manus
    const manusResponse = await manusUtils.postEventToManus(event, eventData);

    console.log(`✅ Event forwarded to Manus: ${event}`);

    res.json({ 
      received: true, 
      event: event,
      manusProcessed: manusResponse.processed 
    });

  } catch (error) {
    console.error('❌ Webhook error:', error);
    res.status(500).json({ 
      error: 'Webhook processing failed',
      message: error.message 
    });
  }
});

// ============ MANUS WEBHOOK RECEIVER ============
router.post('/manus', async (req, res) => {
  try {
    const { eventType, payload } = req.body;

    console.log(`📨 Received Manus webhook: ${eventType}`);

    // Handle different Manus event types
    // This is where you'd process events coming from Manus

    res.json({ received: true, eventType });

  } catch (error) {
    console.error('❌ Manus webhook error:', error);
    res.status(500).json({ error: error.message });
  }
});

module.exports = router;
