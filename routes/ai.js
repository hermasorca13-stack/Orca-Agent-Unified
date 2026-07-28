/**
 * AI Agent Routes - REST API for Hermes
 */

const express = require('express');
const router = express.Router();
const { authenticate } = require('../middleware/auth');
const HermesAIAgent = require('../services/ai-agent');
const KnowledgeBase = require('../services/knowledge-base');
const { logger } = require('../utils/logger');

const agent = new HermesAIAgent();
const kb = new KnowledgeBase();

// ============ REGISTER SAMPLE TOOLS ============
agent.registerTool('fetch-data', async (params) => {
  return { data: 'fetched', params };
}, {
  description: 'Fetch data from external sources',
  parameters: { url: 'string', method: 'string' }
});

agent.registerTool('analyze', async (params) => {
  return { analysis: 'completed', params };
}, {
  description: 'Analyze provided data',
  parameters: { data: 'object' }
});

// ============ THINK ENDPOINT ============
router.post('/think', authenticate, async (req, res) => {
  try {
    const { prompt, context } = req.body;

    const result = await agent.think(prompt, context);

    res.json({
      success: true,
      thinking: result
    });
  } catch (error) {
    logger.error(`AI Think error: ${error.message}`);
    res.status(500).json({ error: error.message });
  }
});

// ============ ACT ENDPOINT ============
router.post('/act', authenticate, async (req, res) => {
  try {
    const { thinking, actions } = req.body;

    const results = await agent.act(thinking, actions);

    res.json({
      success: true,
      results
    });
  } catch (error) {
    logger.error(`AI Act error: ${error.message}`);
    res.status(500).json({ error: error.message });
  }
});

// ============ AUTONOMOUS LOOP ============
router.post('/autonomous', authenticate, async (req, res) => {
  try {
    const { prompt, maxIterations = 5 } = req.body;

    const result = await agent.autonomousLoop(prompt, maxIterations);

    res.json({
      success: true,
      autonomous: result
    });
  } catch (error) {
    logger.error(`AI Autonomous error: ${error.message}`);
    res.status(500).json({ error: error.message });
  }
});

// ============ CHAT ENDPOINT ============
router.post('/chat', authenticate, async (req, res) => {
  try {
    const { message, constraints } = req.body;
    const userId = req.user.userId;

    const response = await agent.chat(userId, message, { constraints });

    res.json({
      success: true,
      chat: response
    });
  } catch (error) {
    logger.error(`AI Chat error: ${error.message}`);
    res.status(500).json({ error: error.message });
  }
});

// ============ KNOWLEDGE BASE - INGEST ============
router.post('/kb/ingest', authenticate, async (req, res) => {
  try {
    const { documents } = req.body;

    if (!Array.isArray(documents) || documents.length === 0) {
      return res.status(400).json({ error: 'Invalid documents format' });
    }

    const results = await kb.batchIngest(documents);

    res.json({
      success: true,
      ingested: results
    });
  } catch (error) {
    logger.error(`KB Ingest error: ${error.message}`);
    res.status(500).json({ error: error.message });
  }
});

// ============ KNOWLEDGE BASE - QUERY ============
router.post('/kb/query', authenticate, async (req, res) => {
  try {
    const { question, topK = 5 } = req.body;

    const result = await kb.queryWithRAG(question, topK);

    res.json({
      success: true,
      rag: result
    });
  } catch (error) {
    logger.error(`KB Query error: ${error.message}`);
    res.status(500).json({ error: error.message });
  }
});

// ============ KNOWLEDGE BASE - STATS ============
router.get('/kb/stats', authenticate, async (req, res) => {
  try {
    const stats = kb.getStats();
    res.json({ success: true, stats });
  } catch (error) {
    logger.error(`KB Stats error: ${error.message}`);
    res.status(500).json({ error: error.message });
  }
});

// ============ TOOLS REGISTRY ============
router.get('/tools', authenticate, (req, res) => {
  const tools = [];
  agent.toolsRegistry.forEach((tool, name) => {
    tools.push({
      name,
      description: tool.metadata.description,
      parameters: tool.metadata.parameters,
      category: tool.metadata.category
    });
  });
  res.json({ success: true, tools });
});

module.exports = router;
