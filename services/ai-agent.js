/**
 * Advanced AI Agent Service - Hermes Intelligence Engine
 * Implements multi-model orchestration, memory management, and autonomous decision-making
 */

const axios = require('axios');
const { eventEmitter } = require('../utils/events');
const { aiModels, selectBestModel, estimateTokens, estimateCost } = require('../config/ai-models');
const VectorStore = require('./vector-store');
const { logger } = require('../utils/logger');

class HermesAIAgent {
  constructor(config = {}) {
    this.config = config;
    this.vectorStore = new VectorStore();
    this.conversationHistory = new Map();
    this.agentMemory = new Map();
    this.toolsRegistry = new Map();
    this.hooks = {
      beforeThink: [],
      afterThink: [],
      beforeAct: [],
      afterAct: []
    };
  }

  // ============ REGISTER TOOLS ============
  registerTool(name, handler, metadata = {}) {
    this.toolsRegistry.set(name, {
      handler,
      metadata: {
        description: metadata.description || '',
        parameters: metadata.parameters || {},
        category: metadata.category || 'general'
      }
    });
    logger.info(`🔧 Tool registered: ${name}`);
  }

  // ============ THINK (Reasoning Phase) ============
  async think(prompt, context = {}) {
    logger.info(`🧠 Hermes thinking on: ${prompt.substring(0, 50)}...`);

    // Execute before hooks
    await Promise.all(this.hooks.beforeThink.map(h => h({ prompt, context })));

    try {
      // Retrieve relevant context from vector store
      const relevantContext = await this.vectorStore.search(prompt, 5);

      // Prepare tools description
      const toolsDescription = this._getToolsDescription();

      // Build thinking prompt
      const thinkingPrompt = `
${context.systemPrompt || 'You are Hermes, an advanced AI agent. Think step by step.'}

Recent context:
${relevantContext.map(r => `- ${r.content}`).join('\n')}

Available tools:
${toolsDescription}

User request: ${prompt}

Reason through this step by step. Then decide what actions to take.
      `;

      const modelConfig = selectBestModel('analysis', context.constraints);
      const thinkingResponse = await this._callModel(modelConfig, thinkingPrompt);

      logger.debug(`💭 Reasoning: ${thinkingResponse.substring(0, 100)}...`);

      // Execute after hooks
      await Promise.all(this.hooks.afterThink.map(h => h({ prompt, reasoning: thinkingResponse })));

      return {
        reasoning: thinkingResponse,
        tokensUsed: estimateTokens(thinkingResponse),
        timestamp: new Date()
      };
    } catch (error) {
      logger.error(`❌ Thinking failed: ${error.message}`);
      throw error;
    }
  }

  // ============ ACT (Execution Phase) ============
  async act(thinking, actions = []) {
    logger.info(`⚡ Hermes acting on ${actions.length} actions`);

    await Promise.all(this.hooks.beforeAct.map(h => h({ thinking, actions })));

    const results = [];

    for (const action of actions) {
      try {
        const tool = this.toolsRegistry.get(action.tool);
        if (!tool) {
          logger.warn(`⚠️  Tool not found: ${action.tool}`);
          continue;
        }

        logger.info(`🎯 Executing: ${action.tool}`);
        const result = await tool.handler(action.params || {});

        results.push({
          tool: action.tool,
          status: 'success',
          result,
          timestamp: new Date()
        });

        eventEmitter.emit('action-executed', { tool: action.tool, result });
      } catch (error) {
        logger.error(`❌ Action failed: ${action.tool} - ${error.message}`);
        results.push({
          tool: action.tool,
          status: 'failed',
          error: error.message,
          timestamp: new Date()
        });
      }
    }

    await Promise.all(this.hooks.afterAct.map(h => h({ thinking, actions, results })));

    return results;
  }

  // ============ OBSERVE (Learning Phase) ============
  async observe(observations) {
    logger.info(`👁️  Hermes observing: ${Object.keys(observations).join(', ')}`);

    // Store in vector database for future context
    for (const [key, value] of Object.entries(observations)) {
      await this.vectorStore.add({
        content: JSON.stringify(value),
        metadata: { key, timestamp: new Date() },
        embedding: `observation-${key}`
      });
    }

    // Update agent memory
    this.agentMemory.set('lastObservation', observations);
    this.agentMemory.set('observationCount', (this.agentMemory.get('observationCount') || 0) + 1);
  }

  // ============ AUTONOMOUS LOOP ============
  async autonomousLoop(initialPrompt, maxIterations = 5) {
    logger.info(`🔄 Starting autonomous loop for: ${initialPrompt}`);

    const conversation = [];
    let currentPrompt = initialPrompt;

    for (let iteration = 0; iteration < maxIterations; iteration++) {
      logger.info(`🔁 Iteration ${iteration + 1}/${maxIterations}`);

      // Think
      const thinking = await this.think(currentPrompt);
      conversation.push({ role: 'agent', type: 'thinking', content: thinking.reasoning });

      // Parse actions from reasoning
      const actions = this._parseActionsFromReasoning(thinking.reasoning);

      if (actions.length === 0) {
        logger.info(`✅ No more actions needed. Task complete.`);
        break;
      }

      // Act
      const results = await this.act(thinking.reasoning, actions);
      conversation.push({ role: 'agent', type: 'actions', content: results });

      // Observe
      const feedback = this._generateFeedback(results);
      await this.observe(feedback);

      // Prepare next iteration
      currentPrompt = `Based on these results: ${JSON.stringify(results)}, what should we do next?`;
    }

    return { conversation, memory: Object.fromEntries(this.agentMemory) };
  }

  // ============ CONVERSATION MANAGEMENT ============
  async chat(userId, message, options = {}) {
    logger.info(`💬 Chat from ${userId}: ${message.substring(0, 50)}...`);

    // Initialize conversation history if needed
    if (!this.conversationHistory.has(userId)) {
      this.conversationHistory.set(userId, []);
    }

    const history = this.conversationHistory.get(userId);

    // Add user message
    history.push({ role: 'user', content: message, timestamp: new Date() });

    // Build prompt with history
    const conversationContext = history
      .slice(-5) // Last 5 messages
      .map(m => `${m.role}: ${m.content}`)
      .join('\n');

    const fullPrompt = `${conversationContext}\nassistant:`;

    // Get response from model
    const modelConfig = selectBestModel('chat', options.constraints);
    const response = await this._callModel(modelConfig, fullPrompt);

    // Add assistant response
    history.push({ role: 'assistant', content: response, timestamp: new Date() });

    // Store in vector DB for learning
    await this.vectorStore.add({
      content: message,
      metadata: { userId, type: 'user-message', timestamp: new Date() },
      embedding: `chat-${userId}-${history.length}`
    });

    return {
      response,
      conversationId: userId,
      tokensUsed: estimateTokens(response),
      cost: estimateCost(modelConfig.id, estimateTokens(fullPrompt), estimateTokens(response))
    };
  }

  // ============ ADD HOOK ============
  addHook(phase, callback) {
    if (this.hooks[phase]) {
      this.hooks[phase].push(callback);
    }
  }

  // ============ PRIVATE METHODS ============
  async _callModel(modelConfig, prompt) {
    const api = process.env.MODEL_API_PROVIDER || 'openai';

    if (api === 'openai') {
      return await this._callOpenAI(modelConfig, prompt);
    } else if (api === 'anthropic') {
      return await this._callAnthropic(modelConfig, prompt);
    } else if (api === 'together') {
      return await this._callTogetherAI(modelConfig, prompt);
    }

    throw new Error(`Unknown API provider: ${api}`);
  }

  async _callOpenAI(modelConfig, prompt) {
    const response = await axios.post(
      'https://api.openai.com/v1/chat/completions',
      {
        model: modelConfig.id,
        messages: [{ role: 'user', content: prompt }],
        temperature: modelConfig.temperature,
        max_tokens: modelConfig.maxTokens
      },
      {
        headers: {
          'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`
        }
      }
    );

    return response.data.choices[0].message.content;
  }

  async _callAnthropic(modelConfig, prompt) {
    const response = await axios.post(
      'https://api.anthropic.com/v1/messages',
      {
        model: modelConfig.id,
        max_tokens: modelConfig.maxTokens,
        system: 'You are Orca Agent, an advanced multi-tier AI framework capable of reasoning, creativity, and autonomous execution.',
        messages: [{ role: 'user', content: prompt }]
      },
      {
        headers: {
          'x-api-key': process.env.ANTHROPIC_API_KEY,
          'anthropic-version': '2023-06-01',
          'content-type': 'application/json'
        }
      }
    );

    return response.data.content[0].text;
  }

  async _callTogetherAI(modelConfig, prompt) {
    const response = await axios.post(
      'https://api.together.xyz/inference',
      {
        model: modelConfig.id,
        prompt: prompt,
        max_tokens: modelConfig.maxTokens,
        temperature: modelConfig.temperature
      },
      {
        headers: {
          'Authorization': `Bearer ${process.env.TOGETHER_API_KEY}`
        }
      }
    );

    return response.data.output.choices[0].text;
  }

  _getToolsDescription() {
    let description = '\nAvailable Tools:\n';
    this.toolsRegistry.forEach((tool, name) => {
      description += `- ${name}: ${tool.metadata.description}\n`;
      description += `  Parameters: ${JSON.stringify(tool.metadata.parameters)}\n`;
    });
    return description;
  }

  _parseActionsFromReasoning(reasoning) {
    // Simple regex-based action parsing
    // In production, use more sophisticated NLP
    const actionRegex = /\[ACTION\]\s*([\w-]+)\s*\{([^}]*)\}/g;
    const actions = [];
    let match;

    while ((match = actionRegex.exec(reasoning)) !== null) {
      actions.push({
        tool: match[1],
        params: this._parseParams(match[2])
      });
    }

    return actions;
  }

  _parseParams(paramString) {
    try {
      return JSON.parse(`{${paramString}}`);
    } catch (e) {
      return {};
    }
  }

  _generateFeedback(results) {
    return {
      successCount: results.filter(r => r.status === 'success').length,
      failureCount: results.filter(r => r.status === 'failed').length,
      results: results
    };
  }
}

module.exports = HermesAIAgent;
