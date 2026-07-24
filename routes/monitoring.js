/**
 * Monitoring & Analytics Routes
 */

const express = require('express');
const router = express.Router();
const { authenticate } = require('../middleware/auth');
const { metricsCollector } = require('../monitoring/metrics');
const { eventEmitter } = require('../utils/events');

// ============ GET METRICS SUMMARY ============
router.get('/metrics/summary', authenticate, (req, res) => {
  const summary = metricsCollector.getSummary();
  res.json({ success: true, metrics: summary });
});

// ============ GET DETAILED REPORT ============
router.get('/metrics/report', authenticate, (req, res) => {
  const { since } = req.query;
  const sinceDate = since ? new Date(since) : null;
  const report = metricsCollector.getDetailedReport(sinceDate);
  res.json({ success: true, report });
});

// ============ GET EVENT HISTORY ============
router.get('/events/history', authenticate, (req, res) => {
  const { eventName, since } = req.query;
  const filter = { eventName };
  if (since) filter.since = new Date(since);

  const history = eventEmitter.getEventHistory(filter);
  res.json({ success: true, events: history.slice(-100) }); // Last 100 events
});

// ============ SYSTEM HEALTH ============
router.get('/health', (req, res) => {
  const summary = metricsCollector.getSummary();
  const errorRate = parseFloat(summary.errorRate);
  const isHealthy = errorRate < 5; // Less than 5% error rate

  res.json({
    status: isHealthy ? 'healthy' : 'degraded',
    health: {
      uptime: summary.uptime,
      errorRate: summary.errorRate,
      avgLatency: summary.avgLatency,
      totalCost: summary.totalCost
    }
  });
});

// ============ ANALYTICS ============
router.get('/analytics', authenticate, (req, res) => {
  const report = metricsCollector.getDetailedReport();
  const requests = report.requests;
  const aiCalls = report.aiCalls;

  // Calculate analytics
  const analytics = {
    requestsByEndpoint: requests.reduce((acc, r) => {
      acc[r.endpoint] = (acc[r.endpoint] || 0) + 1;
      return acc;
    }, {}),
    requestsByStatus: requests.reduce((acc, r) => {
      acc[r.statusCode] = (acc[r.statusCode] || 0) + 1;
      return acc;
    }, {}),
    aiCallsByModel: aiCalls.reduce((acc, a) => {
      acc[a.model] = (acc[a.model] || 0) + 1;
      return acc;
    }, {}),
    avgCostPerAICall: aiCalls.length > 0
      ? (aiCalls.reduce((a, b) => a + b.cost, 0) / aiCalls.length).toFixed(4)
      : 0,
    peakLatency: Math.max(...report.latencies || [0]),
    minLatency: Math.min(...report.latencies || [0])
  };

  res.json({ success: true, analytics });
});

module.exports = router;
