const request = require('supertest');
const app = require('../server');

describe('Health Check', () => {
  describe('GET /api/health', () => {
    it('should return operational status', async () => {
      const res = await request(app)
        .get('/api/health');

      expect(res.status).toBe(200);
      expect(res.body.status).toBe('operational');
      expect(res.body.timestamp).toBeDefined();
      expect(res.body.uptime).toBeDefined();
    });
  });
});
