const request = require('supertest');
const app = require('../server');

describe('Authentication Routes', () => {
  describe('GET /api/auth/verify', () => {
    it('should return error without token', async () => {
      const res = await request(app)
        .get('/api/auth/verify');

      expect(res.status).toBe(401);
      expect(res.body.error).toBeDefined();
    });
  });

  describe('POST /api/auth/logout', () => {
    it('should logout successfully', async () => {
      const res = await request(app)
        .post('/api/auth/logout');

      expect(res.status).toBe(200);
      expect(res.body.message).toBeDefined();
    });
  });
});
