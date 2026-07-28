/**
 * Advanced Rate Limiting Middleware
 */

const SecurityManager = require('../utils/security');

const createRateLimitMiddleware = (maxRequests = 100, windowMs = 60000) => {
  const limiter = SecurityManager.createRateLimiter(maxRequests, windowMs);

  return (req, res, next) => {
    const userId = req.user?.userId || req.ip;
    const checkResult = limiter(userId);

    res.setHeader('X-RateLimit-Limit', maxRequests);
    res.setHeader('X-RateLimit-Window', windowMs);

    if (!checkResult.allowed) {
      res.setHeader('Retry-After', checkResult.retryAfter);
      return res.status(429).json({
        error: 'Too many requests',
        retryAfter: checkResult.retryAfter
      });
    }

    next();
  };
};

module.exports = { createRateLimitMiddleware };
