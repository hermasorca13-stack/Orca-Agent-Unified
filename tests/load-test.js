/**
 * LOAD TESTING & STRESS TESTING SUITE
 * Validates system under high load conditions
 */

const axios = require('axios');
const { performance } = require('perf_hooks');

class LoadTester {
  constructor(baseUrl = 'http://localhost:3000') {
    this.baseUrl = baseUrl;
    this.results = {
      requests: [],
      errors: [],
      metrics: {}
    };
  }

  async runLoadTest(config) {
    console.log('\n' + '='.repeat(80));
    console.log(`🔥 LOAD TEST: ${config.name}`);
    console.log('='.repeat(80));
    console.log(`Concurrent Requests: ${config.concurrency}`);
    console.log(`Total Requests: ${config.totalRequests}`);
    console.log(`Endpoint: ${config.endpoint}`);
    console.log('');

    const startTime = performance.now();
    const results = [];

    for (let i = 0; i < config.totalRequests; i += config.concurrency) {
      const batch = [];
      for (let j = 0; j < config.concurrency && i + j < config.totalRequests; j++) {
        batch.push(this.makeRequest(config));
      }

      const batchResults = await Promise.allSettled(batch);
      results.push(...batchResults);

      // Progress indicator
      const progress = Math.min(i + config.concurrency, config.totalRequests);
      const percent = ((progress / config.totalRequests) * 100).toFixed(1);
      process.stdout.write(`\rProgress: ${progress}/${config.totalRequests} (${percent}%)`);
    }

    const endTime = performance.now();
    const duration = (endTime - startTime) / 1000;

    this.analyzeResults(results, config, duration);
  }

  async makeRequest(config) {
    const startTime = performance.now();
    try {
      const response = await axios[config.method.toLowerCase()](
        `${this.baseUrl}${config.endpoint}`,
        config.data,
        { timeout: config.timeout || 30000 }
      );
      const latency = performance.now() - startTime;
      return {
        status: response.status,
        latency,
        success: response.status >= 200 && response.status < 300
      };
    } catch (error) {
      const latency = performance.now() - startTime;
      return {
        status: error.response?.status || 0,
        latency,
        success: false,
        error: error.message
      };
    }
  }

  analyzeResults(results, config, duration) {
    const successful = results.filter(r => r.value?.success).length;
    const failed = results.length - successful;
    const latencies = results
      .filter(r => r.value?.latency)
      .map(r => r.value.latency)
      .sort((a, b) => a - b);

    const metrics = {
      totalRequests: results.length,
      successful,
      failed,
      failureRate: ((failed / results.length) * 100).toFixed(2),
      duration: duration.toFixed(2),
      requestsPerSecond: (results.length / duration).toFixed(2),
      minLatency: Math.min(...latencies).toFixed(2),
      maxLatency: Math.max(...latencies).toFixed(2),
      avgLatency: (latencies.reduce((a, b) => a + b, 0) / latencies.length).toFixed(2),
      p50Latency: latencies[Math.floor(latencies.length * 0.5)].toFixed(2),
      p95Latency: latencies[Math.floor(latencies.length * 0.95)].toFixed(2),
      p99Latency: latencies[Math.floor(latencies.length * 0.99)].toFixed(2)
    };

    console.log('\n\n📊 TEST RESULTS');
    console.log('-'.repeat(80));
    console.log(`Total Requests: ${metrics.totalRequests}`);
    console.log(`Successful: ${metrics.successful} ✅`);
    console.log(`Failed: ${metrics.failed} ❌`);
    console.log(`Failure Rate: ${metrics.failureRate}%`);
    console.log(`Duration: ${metrics.duration}s`);
    console.log(`Throughput: ${metrics.requestsPerSecond} req/s`);
    console.log('');
    console.log('Latency Statistics:');
    console.log(`  Min: ${metrics.minLatency}ms`);
    console.log(`  Max: ${metrics.maxLatency}ms`);
    console.log(`  Avg: ${metrics.avgLatency}ms`);
    console.log(`  P50: ${metrics.p50Latency}ms`);
    console.log(`  P95: ${metrics.p95Latency}ms`);
    console.log(`  P99: ${metrics.p99Latency}ms`);

    // Status
    const status = metrics.failureRate < 1 && metrics.avgLatency < 500 ? '✅ PASS' : '❌ FAIL';
    console.log(`\n${status}`);

    return metrics;
  }

  static async runAllTests() {
    const tester = new LoadTester();

    console.log('\n🚀 COMPREHENSIVE LOAD TESTING SUITE\n');

    // Test 1: Light Load
    await tester.runLoadTest({
      name: 'Light Load Test',
      endpoint: '/api/health',
      method: 'GET',
      concurrency: 10,
      totalRequests: 100
    });

    // Test 2: Normal Load
    await tester.runLoadTest({
      name: 'Normal Load Test',
      endpoint: '/api/health',
      method: 'GET',
      concurrency: 50,
      totalRequests: 500
    });

    // Test 3: Heavy Load
    await tester.runLoadTest({
      name: 'Heavy Load Test',
      endpoint: '/api/health',
      method: 'GET',
      concurrency: 100,
      totalRequests: 1000
    });

    // Test 4: Stress Test
    await tester.runLoadTest({
      name: 'Stress Test',
      endpoint: '/api/health',
      method: 'GET',
      concurrency: 500,
      totalRequests: 5000
    });
  }
}

// Run if called directly
if (require.main === module) {
  LoadTester.runAllTests().catch(console.error);
}

module.exports = LoadTester;
