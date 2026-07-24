/**
 * Advanced Logging System - Structured Logging with Multiple Outputs
 */

const fs = require('fs');
const path = require('path');

const LOG_LEVELS = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3
};

class HermesLogger {
  constructor(config = {}) {
    this.level = LOG_LEVELS[config.level || 'INFO'];
    this.logFile = config.logFile || 'logs/hermes.log';
    this.maxSize = config.maxSize || 10 * 1024 * 1024; // 10MB
    this._ensureLogDir();
  }

  _ensureLogDir() {
    const dir = path.dirname(this.logFile);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  }

  _format(level, message, meta = {}) {
    const timestamp = new Date().toISOString();
    return JSON.stringify({
      timestamp,
      level,
      message,
      ...meta
    });
  }

  _write(levelName, message, meta) {
    const formatted = this._format(levelName, message, meta);

    // Console output
    console[levelName.toLowerCase()](formatted);

    // File output
    this._writeToFile(formatted);
  }

  _writeToFile(message) {
    try {
      if (fs.existsSync(this.logFile)) {
        const stats = fs.statSync(this.logFile);
        if (stats.size > this.maxSize) {
          const backup = `${this.logFile}.${Date.now()}.backup`;
          fs.renameSync(this.logFile, backup);
        }
      }
      fs.appendFileSync(this.logFile, message + '\n');
    } catch (error) {
      console.error('Failed to write log:', error);
    }
  }

  debug(message, meta = {}) {
    if (this.level <= LOG_LEVELS.DEBUG) {
      this._write('DEBUG', message, meta);
    }
  }

  info(message, meta = {}) {
    if (this.level <= LOG_LEVELS.INFO) {
      this._write('INFO', message, meta);
    }
  }

  warn(message, meta = {}) {
    if (this.level <= LOG_LEVELS.WARN) {
      this._write('WARN', message, meta);
    }
  }

  error(message, meta = {}) {
    if (this.level <= LOG_LEVELS.ERROR) {
      this._write('ERROR', message, meta);
    }
  }
}

const logger = new HermesLogger({
  level: process.env.LOG_LEVEL || 'INFO',
  logFile: process.env.LOG_FILE || 'logs/hermes.log'
});

module.exports = { logger, HermesLogger };
