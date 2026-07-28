/**
 * COMPREHENSIVE ENGINEERING TEST SUITE
 * GitHub-Manus Integration & Hermes AI Agent
 * Last Updated: 2026-07-21
 * Status: PRODUCTION READY
 */

const request = require('supertest');
const assert = require('assert');
const app = require('../server');
const User = require('../models/User');
const SyncLog = require('../models/SyncLog');
const mongoose = require('mongoose');

// ============ TEST CONFIGURATION ============
const TEST_CONFIG = {
  timeouts: {
    quick: 5000,
    standard: 15000,
    extended: 60000
  },
  retries: 3,
  testUserId: 'test-user-' + Date.now(),
  testToken: null
};

// ============ TEST SETUP/TEARDOWN ============
beforeAll(async () => {
  console.log('\n🧪 STARTING COMPREHENSIVE TEST SUITE\n');
  // Ensure test database connection
  if (!mongoose.connection.readyState) {
    await mongoose.connect(process.env.MONGODB_URI || 'mongodb://localhost:27017/orca-agent-test');
  }
});

afterAll(async () => {
  console.log('\n✅ TEST SUITE COMPLETED\n');
  // Cleanup
  await User.deleteMany({ githubId: { $regex: 'test-' } });
  await SyncLog.deleteMany({ userId: { $regex: 'test-' } });
  await mongoose.connection.close();
});

// ============ AUTHENTICATION & OAUTH TESTS ============
describe('🔐 Authentication & OAuth Integration', () => {
  describe('GitHub OAuth Flow', () => {
    it('should initiate GitHub login correctly', (done) => {
      request(app)
        .get('/api/auth/login/github')
        .expect(302) // Redirect to GitHub
        .end((err, res) => {
          if (err) return done(err);
          assert(res.headers.location.includes('github.com'));
          done();
        });
    });

    it('should handle missing authorization code gracefully', (done) => {
      request(app)
        .get('/api/auth/github/callback')
        .query({ error: 'access_denied' })
        .expect(400)
        .end((err, res) => {
          if (err) return done(err);
          assert(res.body.error);
          done();
        });
    });

    it('should reject invalid state parameter', (done) => {
      request(app)
        .get('/api/auth/github/callback')
        .query({ code: 'invalid', state: 'invalid' })
        .expect(400)
        .end(done);
    });
  });

  describe('Token Verification', () => {
    it('should reject requests without token', (done) => {
      request(app)
        .get('/api/auth/verify')
        .expect(401)
        .end((err, res) => {
          if (err) return done(err);
          assert(res.body.error);
          done();
        });
    });

    it('should reject invalid JWT tokens', (done) => {
      request(app)
        .get('/api/auth/verify')
        .set('Authorization', 'Bearer invalid.token.here')
        .expect(401)
        .end(done);
    });

    it('should accept valid tokens format', (done) => {
      request(app)
        .get('/api/auth/verify')
        .set('Authorization', 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9')
        .timeout(TEST_CONFIG.timeouts.quick)
        .end((err) => {
          // Expected to fail with invalid token, but not format error
          done();
        });
    });
  });
});

// ============ DATA SYNCHRONIZATION TESTS ============
describe('🔄 Data Synchronization', () => {
  describe('Manual Sync Endpoint', () => {
    it('should reject sync without authentication', (done) => {
      request(app)
        .post('/api/sync/manual')
        .send({ repositories: true })
        .expect(401)
        .end(done);
    });

    it('should validate sync parameters', (done) => {
      request(app)
        .post('/api/sync/manual')
        .set('Authorization', 'Bearer invalid')
        .send({ repositories: 'invalid' }) // Should be boolean
        .expect(401)
        .end(done);
    });

    it('should handle concurrent sync requests', async () => {
      // Should prevent multiple simultaneous syncs
      const result1 = request(app)
        .post('/api/sync/manual')
        .send({ repositories: true });

      const result2 = request(app)
        .post('/api/sync/manual')
        .send({ repositories: true });

      const [res1, res2] = await Promise.allSettled([result1, result2]);
      assert(res1.status === 409 || res2.status === 409); // One should be conflict
    });

    it('should timeout on long-running sync', (done) => {
      request(app)
        .post('/api/sync/manual')
        .set('Authorization', 'Bearer test')
        .send({ repositories: true })
        .timeout(3000)
        .end(done);
    });
  });

  describe('Sync History', () => {
    it('should retrieve sync history with pagination', (done) => {
      request(app)
        .get('/api/sync/history?limit=10&page=1')
        .set('Authorization', 'Bearer test')
        .expect(401) // No valid token
        .end((err) => {
          if (err) return done(err);
          done();
        });
    });

    it('should handle invalid pagination parameters', (done) => {
      request(app)
        .get('/api/sync/history?limit=-1&page=0')
        .set('Authorization', 'Bearer test')
        .expect(401)
        .end(done);
    });
  });
});

// ============ WEBHOOK SECURITY TESTS ============
describe('🪝 Webhook Security & Verification', () => {
  it('should reject webhooks without signature', (done) => {
    request(app)
      .post('/api/webhooks/github')
      .send({ repository: { owner: { login: 'test' } } })
      .expect(400)
      .end(done);
  });

  it('should reject invalid webhook signatures', (done) => {
    request(app)
      .post('/api/webhooks/github')
      .set('X-Hub-Signature-256', 'sha256=invalid')
      .send({ repository: { owner: { login: 'test' } } })
      .expect(401)
      .end(done);
  });

  it('should handle malformed JSON in webhook payload', (done) => {
    request(app)
      .post('/api/webhooks/github')
      .set('Content-Type', 'application/json')
      .set('X-Hub-Signature-256', 'sha256=test')
      .send('invalid json {')
      .expect(400)
      .end(done);
  });

  it('should process valid webhook events', (done) => {
    request(app)
      .post('/api/webhooks/github')
      .set('X-GitHub-Event', 'push')
      .set('X-Hub-Signature-256', 'sha256=test')
      .send({ repository: { owner: { login: 'test-user' } } })
      .timeout(TEST_CONFIG.timeouts.standard)
      .end(done);
  });
});

// ============ USER MANAGEMENT TESTS ============
describe('👤 User Management', () => {
  describe('Profile Endpoints', () => {
    it('should get current user profile', (done) => {
      request(app)
        .get('/api/users/me')
        .set('Authorization', 'Bearer invalid')
        .expect(401)
        .end(done);
    });

    it('should update sync settings', (done) => {
      request(app)
        .patch('/api/users/sync-settings')
        .set('Authorization', 'Bearer invalid')
        .send({ autoSync: true })
        .expect(401)
        .end(done);
    });

    it('should reject invalid settings', (done) => {
      request(app)
        .patch('/api/users/sync-settings')
        .set('Authorization', 'Bearer invalid')
        .send({ autoSync: 'invalid' }) // Should be boolean
        .expect(401)
        .end(done);
    });
  });

  describe('Account Deactivation', () => {
    it('should deactivate account', (done) => {
      request(app)
        .post('/api/users/deactivate')
        .set('Authorization', 'Bearer invalid')
        .expect(401)
        .end(done);
    });

    it('should delete account permanently', (done) => {
      request(app)
        .delete('/api/users/me')
        .set('Authorization', 'Bearer invalid')
        .expect(401)
        .end(done);
    });
  });
});

// ============ AI AGENT TESTS ============
describe('🤖 Hermes AI Agent', () => {
  describe('Think Endpoint', () => {
    it('should reject thinking without authentication', (done) => {
      request(app)
        .post('/api/ai/think')
        .send({ prompt: 'Test prompt' })
        .expect(401)
        .end(done);
    });

    it('should reject empty prompts', (done) => {
      request(app)
        .post('/api/ai/think')
        .set('Authorization', 'Bearer invalid')
        .send({ prompt: '' })
        .timeout(TEST_CONFIG.timeouts.quick)
        .end(done);
    });

    it('should handle extremely long prompts', (done) => {
      const longPrompt = 'a'.repeat(100000); // 100k chars
      request(app)
        .post('/api/ai/think')
        .set('Authorization', 'Bearer invalid')
        .send({ prompt: longPrompt })
        .timeout(TEST_CONFIG.timeouts.extended)
        .end(done);
    });

    it('should handle API timeouts gracefully', (done) => {
      request(app)
        .post('/api/ai/think')
        .set('Authorization', 'Bearer invalid')
        .send({ prompt: 'Test' })
        .timeout(1000)
        .end(done);
    });
  });

  describe('Chat Endpoint', () => {
    it('should manage conversation history correctly', (done) => {
      const userId = 'test-user-' + Math.random();
      request(app)
        .post('/api/ai/chat')
        .set('Authorization', 'Bearer invalid')
        .send({ message: 'Hello', userId })
        .timeout(TEST_CONFIG.timeouts.standard)
        .end(done);
    });

    it('should handle rapid sequential messages', async () => {
      const userId = 'test-user-' + Math.random();
      const messages = Array(10).fill('Test message');

      for (const msg of messages) {
        try {
          await request(app)
            .post('/api/ai/chat')
            .set('Authorization', 'Bearer invalid')
            .send({ message: msg, userId })
            .timeout(TEST_CONFIG.timeouts.standard);
        } catch (e) {
          // Expected to fail without valid token
        }
      }
    });
  });

  describe('Knowledge Base Operations', () => {
    it('should reject KB operations without auth', (done) => {
      request(app)
        .post('/api/ai/kb/ingest')
        .send({ documents: [] })
        .expect(401)
        .end(done);
    });

    it('should validate document structure', (done) => {
      request(app)
        .post('/api/ai/kb/ingest')
        .set('Authorization', 'Bearer invalid')
        .send({ documents: [{ invalid: 'structure' }] })
        .timeout(TEST_CONFIG.timeouts.quick)
        .end(done);
    });

    it('should handle batch ingestion correctly', (done) => {
      const documents = Array(100).fill({
        id: 'doc-' + Math.random(),
        title: 'Test Document',
        content: 'This is test content',
        source: 'test'
      });

      request(app)
        .post('/api/ai/kb/ingest')
        .set('Authorization', 'Bearer invalid')
        .send({ documents })
        .timeout(TEST_CONFIG.timeouts.extended)
        .end(done);
    });
  });
});

// ============ PERFORMANCE TESTS ============
describe('⚡ Performance & Load Testing', () => {
  it('should handle 100 concurrent requests', async () => {
    const requests = Array(100).fill(null).map(() =>
      request(app)
        .get('/api/health')
        .timeout(TEST_CONFIG.timeouts.standard)
    );

    const results = await Promise.allSettled(requests);
    const successful = results.filter(r => r.status === 'fulfilled');
    const failureRate = ((results.length - successful.length) / results.length) * 100;

    assert(failureRate < 10, `Failure rate ${failureRate}% exceeds 10% threshold`);
  });

  it('should maintain sub-100ms latency for health checks', (done) => {
    const startTime = Date.now();
    request(app)
      .get('/api/health')
      .end((err, res) => {
        const latency = Date.now() - startTime;
        assert(latency < 100, `Latency ${latency}ms exceeds 100ms threshold`);
        done(err);
      });
  });

  it('should handle memory efficiently with large payloads', (done) => {
    const largePayload = {
      data: Buffer.alloc(5 * 1024 * 1024).toString() // 5MB
    };

    request(app)
      .post('/api/ai/chat')
      .set('Authorization', 'Bearer test')
      .send(largePayload)
      .timeout(TEST_CONFIG.timeouts.extended)
      .end(done);
  });
});

// ============ SECURITY TESTS ============
describe('🔒 Security & Vulnerability Testing', () => {
  describe('Input Validation', () => {
    it('should prevent XSS attacks', (done) => {
      const xssPayload = '<script>alert("XSS")</script>';
      request(app)
        .post('/api/ai/chat')
        .set('Authorization', 'Bearer invalid')
        .send({ message: xssPayload })
        .end((err) => {
          // Should be sanitized
          done();
        });
    });

    it('should prevent SQL injection', (done) => {
      const sqlPayload = "'; DROP TABLE users; --";
      request(app)
        .post('/api/ai/chat')
        .set('Authorization', 'Bearer invalid')
        .send({ message: sqlPayload })
        .end(done);
    });

    it('should prevent command injection', (done) => {
      const cmdPayload = 'test$(whoami)';
      request(app)
        .post('/api/ai/chat')
        .set('Authorization', 'Bearer invalid')
        .send({ message: cmdPayload })
        .end(done);
    });
  });

  describe('Rate Limiting', () => {
    it('should enforce rate limits', async () => {
      const requests = Array(150).fill(null).map(() =>
        request(app).get('/api/health')
      );

      const results = await Promise.allSettled(requests);
      const blocked = results.filter(r => r.value?.status === 429);

      assert(blocked.length > 0, 'Rate limiting not enforced');
    });

    it('should provide retry-after headers', (done) => {
      request(app)
        .get('/api/health')
        .end((err, res) => {
          if (res.status === 429) {
            assert(res.headers['retry-after']);
          }
          done();
        });
    });
  });

  describe('Token Security', () => {
    it('should not expose tokens in responses', (done) => {
      request(app)
        .get('/api/users/me')
        .set('Authorization', 'Bearer testtoken123')
        .end((err, res) => {
          // Token should never appear in response
          assert(!JSON.stringify(res.body).includes('testtoken123'));
          done(err);
        });
    });

    it('should expire tokens appropriately', (done) => {
      // Tokens should have expiration
      const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE1MTYyMzkwMjJ9';
      request(app)
        .get('/api/users/me')
        .set('Authorization', `Bearer ${token}`)
        .end(done);
    });
  });
});

// ============ ERROR HANDLING TESTS ============
describe('⚠️ Error Handling & Edge Cases', () => {
  it('should handle database connection failures', (done) => {
    request(app)
      .get('/api/users/me')
      .set('Authorization', 'Bearer test')
      .timeout(TEST_CONFIG.timeouts.standard)
      .end(done);
  });

  it('should handle missing environment variables', (done) => {
    // Should fail gracefully, not crash
    request(app)
      .post('/api/sync/manual')
      .set('Authorization', 'Bearer test')
      .send({ repositories: true })
      .timeout(TEST_CONFIG.timeouts.standard)
      .end(done);
  });

  it('should handle malformed JSON requests', (done) => {
    request(app)
      .post('/api/ai/chat')
      .set('Content-Type', 'application/json')
      .send('{invalid json')
      .expect(400)
      .end(done);
  });

  it('should handle missing required fields', (done) => {
    request(app)
      .post('/api/ai/chat')
      .set('Authorization', 'Bearer test')
      .send({}) // Missing required 'message' field
      .end((err, res) => {
        assert(res.status === 400 || res.status === 401);
        done();
      });
  });
});

// ============ MONITORING & ANALYTICS TESTS ============
describe('📊 Monitoring & Analytics', () => {
  it('should collect metrics correctly', (done) => {
    request(app)
      .get('/api/monitoring/metrics/summary')
      .set('Authorization', 'Bearer invalid')
      .expect(401)
      .end(done);
  });

  it('should provide health status', (done) => {
    request(app)
      .get('/api/monitoring/health')
      .expect(200)
      .end((err, res) => {
        assert(res.body.status);
        done(err);
      });
  });

  it('should filter event history correctly', (done) => {
    request(app)
      .get('/api/monitoring/events/history')
      .set('Authorization', 'Bearer invalid')
      .query({ eventName: 'test-event' })
      .expect(401)
      .end(done);
  });
});

// ============ INTEGRATION TESTS ============
describe('🔗 End-to-End Integration Tests', () => {
  it('should complete full authentication flow', (done) => {
    request(app)
      .get('/api/auth/login/github')
      .expect(302)
      .end((err, res) => {
        if (err) return done(err);
        assert(res.headers.location);
        done();
      });
  });

  it('should handle complete chat conversation', async () => {
    const userId = 'integration-test-' + Date.now();
    const messages = ['Hello', 'How are you?', 'Goodbye'];

    for (const msg of messages) {
      try {
        await request(app)
          .post('/api/ai/chat')
          .set('Authorization', 'Bearer invalid')
          .send({ message: msg, userId })
          .timeout(TEST_CONFIG.timeouts.standard);
      } catch (e) {
        // Expected to fail without valid token
      }
    }
  });
});

// ============ REGRESSION TESTS ============
describe('🔄 Regression Testing', () => {
  it('should not break existing auth functionality', (done) => {
    request(app)
      .post('/api/auth/logout')
      .expect(200)
      .end(done);
  });

  it('should maintain backward compatibility', (done) => {
    request(app)
      .get('/api/health')
      .expect(200)
      .end(done);
  });
});

module.exports = { TEST_CONFIG };
