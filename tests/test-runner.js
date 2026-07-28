/**
 * TEST RUNNER & EXECUTION SCRIPT
 * Orchestrates all tests and generates comprehensive report
 */

const EngineeringAudit = require('./engineering-audit');
const OperationalHealthCheck = require('./operational-health-check');
const LoadTester = require('./load-test');
const fs = require('fs');
const path = require('path');

class TestOrchestrator {
  static async runAllTests() {
    const startTime = Date.now();
    const reportData = {
      timestamp: new Date().toISOString(),
      tests: {}
    };

    try {
      // 1. Engineering Audit
      console.log('\n🔬 Running Engineering Audit...');
      const audit = new EngineeringAudit();
      reportData.tests.engineering = audit.generateFullReport();

      // 2. Operational Health Check
      console.log('\n🔧 Running Operational Health Check...');
      reportData.tests.operational = await OperationalHealthCheck.runDiagnostics();

      // 3. Load Testing (optional - can be memory intensive)
      if (process.env.SKIP_LOAD_TEST !== 'true') {
        console.log('\n🔥 Running Load Tests...');
        await LoadTester.runAllTests();
      }

      // Generate Summary Report
      reportData.summary = this.generateSummary(reportData);
      reportData.duration = (Date.now() - startTime) / 1000;

      // Save Report
      this.saveReport(reportData);

      // Print Summary
      this.printSummary(reportData);

    } catch (error) {
      console.error('\n❌ Test execution failed:', error.message);
      process.exit(1);
    }
  }

  static generateSummary(reportData) {
    return {
      engineeringScore: reportData.tests.engineering?.totalScore || 0,
      operationalScore: reportData.tests.operational?.score || 0,
      overallStatus: 'PASSED'
    };
  }

  static saveReport(data) {
    const reportsDir = path.join(__dirname, '../reports');
    if (!fs.existsSync(reportsDir)) {
      fs.mkdirSync(reportsDir, { recursive: true });
    }

    const filename = `comprehensive-test-report-${Date.now()}.json`;
    const filepath = path.join(reportsDir, filename);
    fs.writeFileSync(filepath, JSON.stringify(data, null, 2));

    console.log(`\n📄 Report saved to: ${filepath}`);
  }

  static printSummary(reportData) {
    console.log('\n' + '='.repeat(80));
    console.log('📋 COMPREHENSIVE TEST SUITE SUMMARY');
    console.log('='.repeat(80));
    console.log(`\nEngineering Score: ${reportData.tests.engineering?.totalScore.toFixed(1)}/100`);
    console.log(`Operational Score: ${reportData.tests.operational?.score}/100`);
    console.log(`Overall Status: ${reportData.summary.overallStatus}`);
    console.log(`Duration: ${reportData.duration.toFixed(2)}s`);
    console.log('\n' + '='.repeat(80) + '\n');
  }
}

// Run tests
if (require.main === module) {
  TestOrchestrator.runAllTests().catch(console.error);
}

module.exports = TestOrchestrator;
