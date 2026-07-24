/**
 * Event Emitter System - Centralized Event Management
 */

const EventEmitter = require('events');

class HermesEventEmitter extends EventEmitter {
  constructor() {
    super();
    this.eventLog = [];
    this.maxLogSize = 10000;
  }

  emit(eventName, data) {
    // Log event
    this.eventLog.push({
      eventName,
      data,
      timestamp: new Date()
    });

    // Keep log manageable
    if (this.eventLog.length > this.maxLogSize) {
      this.eventLog.shift();
    }

    return super.emit(eventName, data);
  }

  getEventHistory(filter = {}) {
    let history = this.eventLog;

    if (filter.eventName) {
      history = history.filter(e => e.eventName === filter.eventName);
    }

    if (filter.since) {
      history = history.filter(e => e.timestamp > filter.since);
    }

    return history;
  }

  clearEventLog() {
    this.eventLog = [];
  }
}

const eventEmitter = new HermesEventEmitter();

module.exports = { eventEmitter };
