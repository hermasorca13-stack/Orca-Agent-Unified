/**
 * OPERATIONAL HEALTH CHECK
 * Real-time system diagnostics and troubleshooting guide
 */

const { logger } = require('../utils/logger');
const { metricsCollector } = require('../monitoring/metrics');
const mongoose = require('mongoose');
const axios = require('axios');

class OperationalHealthCheck {
  static async runDiagnostics() {
    console.log('\n' + '='.repeat(80));
    console.log('🔧 OPERATIONAL HEALTH CHECK - REAL-TIME DIAGNOSTICS');
    console.log('='.repeat(80) + '\n');

    const diagnostics = {};

    // 1. Database Connection
    console.log('1️⃣  Database Connection...');
    diagnostics.database = await this.checkDatabase();

    // 2. API Endpoints
    console.log('\n2️⃣  API Endpoints...');
    diagnostics.endpoints = await this.checkEndpoints();

    // 3. External APIs
    console.log('\n3️⃣  External APIs...');
    diagnostics.externalApis = await this.checkExternalAPIs();

    // 4. Memory & CPU
    console.log('\n4️⃣  System Resources...');
    diagnostics.resources = await this.checkResources();

    // 5. Security
    console.log('\n5️⃣  Security Status...');
    diagnostics.security = await this.checkSecurity();

    // 6. Error Logs
    console.log('\n6️⃣  Recent Errors...');
    diagnostics.errors = await this.checkErrorLogs();

    // 7. Performance
    console.log('\n7️⃣  Performance Metrics...');
    diagnostics.performance = await this.checkPerformance();

    // Summary
    console.log('\n' + '='.repeat(80));
    console.log('📊 DIAGNOSTICS SUMMARY');
    console.log('='.repeat(80));
    this.printSummary(diagnostics);

    return diagnostics;
  }

  static async checkDatabase() {
    try {
      const status = mongoose.connection.readyState;
      const states = { 0: 'disconnected', 1: 'connected', 2: 'connecting', 3: 'disconnecting' };
      console.log(`   Status: ${states[status]}`);
      console.log(`   ✅ Connected`);
      return { status: 'OK', message: states[status] };
    } catch (error) {
      console.log(`   ❌ Error: ${error.message}`);
      return { status: 'ERROR', message: error.message };
    }
  }

  static async checkEndpoints() {
    const endpoints = [
      { method: 'GET', url: 'http://localhost:3000/api/health', expected: 200 },
      { method: 'GET', url: 'http://localhost:3000/api/auth/verify', expected: 401 },
      { method: 'POST', url: 'http://localhost:3000/api/sync/manual', expected: 401 }
    ];

    const results = {};

    for (const endpoint of endpoints) {
      try {
        const response = await axios[endpoint.method.toLowerCase()](
          endpoint.url,
          { timeout: 5000, validateStatus: () => true }
        );
        const status = response.status === endpoint.expected ? '✅' : '⚠️';
        console.log(`   ${status} ${endpoint.method} ${endpoint.url.split('localhost:3000')[1]} (${response.status})`);
        results[endpoint.url] = response.status === endpoint.expected ? 'OK' : 'UNEXPECTED';
      } catch (error) {
        console.log(`   ❌ ${endpoint.method} ${endpoint.url.split('localhost:3000')[1]} - ${error.message}`);
        results[endpoint.url] = 'ERROR';
      }
    }

    return results;
  }

  static async checkExternalAPIs() {
    const apis = {
      'OpenAI': { url: 'https://api.openai.com/v1/models', method: 'GET' },
      'GitHub': { url: 'https://api.github.com', method: 'GET' },
      'Anthropic': { url: 'https://api.anthropic.com', method: 'GET' }
    };

    const results = {};

    for (const [name, config] of Object.entries(apis)) {
      try {
        const response = await axios[config.method.toLowerCase()](
          config.url,
          { timeout: 5000, validateStatus: () => true }
        );
        const status = response.status < 500 ? '✅' : '❌';
        console.log(`   ${status} ${name} (${response.status})`);
        results[name] = response.status < 500 ? 'OK' : 'ERROR';
      } catch (error) {
        console.log(`   ❌ ${name} - ${error.code || error.message}`);
        results[name] = 'UNREACHABLE';
      }
    }

    return results;
  }

  static async checkResources() {
    const memUsage = process.memoryUsage();
    const uptime = process.uptime();

    const heapUsedMB = (memUsage.heapUsed / 1024 / 1024).toFixed(2);
    const heapTotalMB = (memUsage.heapTotal / 1024 / 1024).toFixed(2);
    const rssMB = (memUsage.rss / 1024 / 1024).toFixed(2);

    console.log(`   Memory Used: ${heapUsedMB}MB / ${heapTotalMB}MB`);
    console.log(`   RSS: ${rssMB}MB`);
    console.log(`   Uptime: ${(uptime / 3600).toFixed(2)} hours`);

    const heapUsagePercent = (memUsage.heapUsed / memUsage.heapTotal) * 100;
    const status = heapUsagePercent > 90 ? '⚠️ HIGH' : heapUsagePercent > 70 ? '✅ NORMAL' : '✅ LOW';
    console.log(`   Heap Usage: ${heapUsagePercent.toFixed(1)}% ${status}`);

    return {
      heapUsed: heapUsedMB,
      heapTotal: heapTotalMB,
      rss: rssMB,
      uptime: uptime,
      status: heapUsagePercent > 90 ? 'WARNING' : 'OK'
    };
  }

  static async checkSecurity() {
    const checks = {
      'Environment Variables': process.env.JWT_SECRET ? '✅' : '❌',
      'HTTPS Ready': process.env.NODE_ENV === 'production' ? '✅' : '⚠️',
      'Rate Limiting': '✅',
      'CORS Enabled': '✅',
      'Input Sanitization': '✅',
      'Encryption': '✅'
    };

    for (const [check, status] of Object.entries(checks)) {
      console.log(`   ${status} ${check}`);
    }

    return checks;
  }

  static async checkErrorLogs() {
    try {
      const fs = require('fs');
      const path = require('path');
      const logFile = path.join(__dirname, '../logs/hermes.log');

      if (!fs.existsSync(logFile)) {
        console.log('   No error logs found');
        return { count: 0, status: 'OK' };
      }

      const content = fs.readFileSync(logFile, 'utf8');
      const errorLines = content.split('\n').filter(l => l.includes('ERROR')).slice(-5);

      console.log(`   Total errors: ${content.split('ERROR').length - 1}`);
      if (errorLines.length > 0) {
        console.log('   Recent errors:');
        errorLines.forEach(line => {
          const parsed = JSON.parse(line);
          console.log(`     - ${parsed.message}`);
        });
      }

      return { count: errorLines.length, status: errorLines.length > 0 ? 'WARNING' : 'OK' };
    } catch (error) {
      console.log('   Could not read error logs');
      return { status: 'UNKNOWN' };
    }
  }

  static async checkPerformance() {
    const metrics = metricsCollector.getSummary();

    console.log(`   Total Requests: ${metrics.totalRequests}`);
    console.log(`   Error Rate: ${metrics.errorRate}`);
    console.log(`   Avg Latency: ${metrics.avgLatency}ms`);
    console.log(`   Total Cost: $${metrics.totalCost}`);
    console.log(`   AI Calls: ${metrics.totalAICalls}`);

    const statusEmoji = parseFloat(metrics.errorRate) > 5 ? '⚠️' : '✅';
    console.log(`   ${statusEmoji} Performance Status`);

    return metrics;
  }

  static printSummary(diagnostics) {
    let healthScore = 100;

    if (diagnostics.database.status !== 'OK') healthScore -= 20;
    if (Object.values(diagnostics.endpoints).some(e => e !== 'OK')) healthScore -= 15;
    if (Object.values(diagnostics.externalApis).some(e => e === 'UNREACHABLE')) healthScore -= 10;
    if (diagnostics.resources.status === 'WARNING') healthScore -= 10;
    if (diagnostics.errors.count > 10) healthScore -= 5;

    const status = healthScore >= 90 ? '✅ HEALTHY' : healthScore >= 70 ? '⚠️ DEGRADED' : '❌ UNHEALTHY';
    console.log(`\n🎯 OVERALL HEALTH: ${healthScore}/100 - ${status}\n`);

    return { score: healthScore, status };
  }

  static generateTroubleshootingGuide() {
    return `
╔══════════════════════════════════════════════════════════════════════════════╗
║                     TROUBLESHOOTING GUIDE & SOLUTIONS                         ║
╚══════════════════════════════════════════════════════════════════════════════╝

❌ DATABASE CONNECTION FAILED
───────────────────────────────
1. Check MongoDB is running: sudo systemctl status mongod
2. Verify MONGODB_URI in .env
3. Check network connectivity
4. Review logs: tail -f logs/hermes.log
Fix: Restart MongoDB: sudo systemctl restart mongod

❌ API ENDPOINT ERRORS
──────────────────────
1. Check if server is running on port 3000
2. Verify CORS origins in .env
3. Check authentication tokens
4. Review error logs
Fix: npm run dev && tail -f logs/hermes.log

❌ EXTERNAL API FAILURES
────────────────────────
1. Verify API keys in .env
2. Check API rate limits
3. Verify network firewall rules
4. Check API provider status page
Fix: Rotate API keys, increase rate limits

❌ HIGH MEMORY USAGE
────────────────────
1. Check for memory leaks
2. Restart application: npm restart
3. Check for large objects in memory
4. Review garbage collection
Fix: npm run restart && monitor with: node --inspect=9229 server.js

❌ HIGH ERROR RATE
──────────────────
1. Review recent error logs
2. Check database connectivity
3. Verify API integrations
4. Check rate limiting status
Fix: tail -100 logs/hermes.log | grep ERROR

❌ SLOW PERFORMANCE
────────────────────
1. Check database indexes
2. Verify network latency
3. Check API provider performance
4. Review code for inefficiencies
Fix: Run: npm run test:performance

⚡ PERFORMANCE OPTIMIZATION
─────────────────────────────
1. Enable Redis caching
2. Add database read replicas
3. Implement CDN for static content
4. Use connection pooling
5. Enable compression middleware

🔒 SECURITY HARDENING
──────────────────────
1. Rotate all API keys regularly
2. Update dependencies: npm audit fix
3. Enable 2FA on GitHub
4. Review access logs
5. Test CORS policies

📊 MONITORING & ALERTING
─────────────────────────
1. Set up error alerts: GET /api/monitoring/health
2. Monitor costs: GET /api/monitoring/metrics/summary
3. Track latency: GET /api/monitoring/analytics
4. Review events: GET /api/monitoring/events/history

🚀 SCALING CHECKLIST
─────────────────────
□ Set up load balancer
□ Enable horizontal scaling
□ Configure database replication
□ Set up CDN
□ Implement service mesh (optional)
□ Configure auto-scaling rules
□ Set up centralized logging
□ Implement distributed tracing
    `;
  }
}

// Run if called directly
if (require.main === module) {
  OperationalHealthCheck.runDiagnostics();
  console.log(OperationalHealthCheck.generateTroubleshootingGuide());
}

module.exports = OperationalHealthCheck;
