/**
 * Advanced Metrics & Monitoring System
 * Tracks AI performance, costs, latency, and system health
 */

class MetricsCollector {
  constructor() {
    this.metrics = {
      requests: [],
      aiCalls: [],
      errors: [],
      latencies: [],
      costs: []
    };
    this.startTime = Date.now();
  }

  // ============ TRACK REQUEST ============
  trackRequest(endpoint, method, statusCode, duration) {
    this.metrics.requests.push({
      endpoint,
      method,
      statusCode,
      duration,
      timestamp: new Date()
    });
  }

  // ============ TRACK AI CALL ============
  trackAICall(model, tokens, cost, duration) {
    this.metrics.aiCalls.push({
      model,
      tokens,
      cost,
      duration,
      timestamp: new Date()
    });
    this.metrics.costs.push(cost);
    this.metrics.latencies.push(duration);
  }

  // ============ TRACK ERROR ============
  trackError(type, message, context) {
    this.metrics.errors.push({
      type,
      message,
      context,
      timestamp: new Date()
    });
  }

  // ============ GET SUMMARY ============
  getSummary() {
    const totalCost = this.metrics.costs.reduce((a, b) => a + b, 0);
    const avgLatency = this.metrics.latencies.length > 0
      ? this.metrics.latencies.reduce((a, b) => a + b, 0) / this.metrics.latencies.length
      : 0;

    return {
      uptime: Date.now() - this.startTime,
      totalRequests: this.metrics.requests.length,
      totalAICalls: this.metrics.aiCalls.length,
      totalErrors: this.metrics.errors.length,
      totalCost: totalCost.toFixed(4),
      avgLatency: avgLatency.toFixed(2),
      errorRate: ((this.metrics.errors.length / this.metrics.requests.length) * 100).toFixed(2) + '%'
    };
  }

  // ============ GET DETAILED REPORT ============
  getDetailedReport(since = null) {
    let requests = this.metrics.requests;
    let aiCalls = this.metrics.aiCalls;
    let errors = this.metrics.errors;

    if (since) {
      requests = requests.filter(r => r.timestamp > since);
      aiCalls = aiCalls.filter(a => a.timestamp > since);
      errors = errors.filter(e => e.timestamp > since);
    }

    return {
      summary: this.getSummary(),
      requests: requests.slice(-50), // Last 50
      aiCalls: aiCalls.slice(-50),
      errors: errors.slice(-50),
      period: { since, until: new Date() }
    };
  }
}

const metricsCollector = new MetricsCollector();

module.exports = { metricsCollector, MetricsCollector };
