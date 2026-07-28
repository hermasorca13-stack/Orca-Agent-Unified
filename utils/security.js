/**
 * Military-Grade Security Utilities
 * Encryption, Hashing, Token Management
 */

const crypto = require('crypto');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');

class SecurityManager {
  // ============ ENCRYPTION ============
  static encrypt(text, secret) {
    const iv = crypto.randomBytes(16);
    const cipher = crypto.createCipheriv(
      'aes-256-cbc',
      Buffer.from(secret.padEnd(32, '0').substring(0, 32)),
      iv
    );

    let encrypted = cipher.update(text, 'utf8', 'hex');
    encrypted += cipher.final('hex');

    return `${iv.toString('hex')}:${encrypted}`;
  }

  static decrypt(encryptedText, secret) {
    const [ivHex, encrypted] = encryptedText.split(':');
    const iv = Buffer.from(ivHex, 'hex');
    const decipher = crypto.createDecipheriv(
      'aes-256-cbc',
      Buffer.from(secret.padEnd(32, '0').substring(0, 32)),
      iv
    );

    let decrypted = decipher.update(encrypted, 'hex', 'utf8');
    decrypted += decipher.final('utf8');

    return decrypted;
  }

  // ============ HASHING ============
  static async hashPassword(password) {
    return bcrypt.hash(password, 12);
  }

  static async comparePassword(password, hash) {
    return bcrypt.compare(password, hash);
  }

  // ============ JWT TOKENS ============
  static generateToken(payload, secret, expiresIn = '24h') {
    return jwt.sign(payload, secret, { expiresIn });
  }

  static verifyToken(token, secret) {
    try {
      return jwt.verify(token, secret);
    } catch (error) {
      return null;
    }
  }

  // ============ RATE LIMITING ============
  static createRateLimiter(maxRequests = 100, windowMs = 60000) {
    const requests = new Map();

    return (userId) => {
      const now = Date.now();
      const userRequests = requests.get(userId) || [];

      // Clean old requests
      const recentRequests = userRequests.filter(t => now - t < windowMs);

      if (recentRequests.length >= maxRequests) {
        return {
          allowed: false,
          retryAfter: Math.ceil((recentRequests[0] + windowMs - now) / 1000)
        };
      }

      recentRequests.push(now);
      requests.set(userId, recentRequests);

      return { allowed: true };
    };
  }

  // ============ SECURE RANDOM ============
  static generateSecureToken(length = 32) {
    return crypto.randomBytes(length).toString('hex');
  }

  // ============ INPUT VALIDATION ============
  static sanitizeInput(input) {
    if (typeof input !== 'string') return input;
    return input
      .replace(/[<>"']/g, '') // Remove HTML chars
      .trim()
      .substring(0, 1000); // Limit length
  }
}

module.exports = SecurityManager;
