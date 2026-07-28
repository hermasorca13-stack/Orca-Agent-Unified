/**
 * AI Models Configuration - Advanced Neural Network Integration
 * Supports: GPT-4, Claude-3, LLaMA-2, Cohere, Anthropic
 */

const aiModels = {
  // ============ OPENAI GPT FAMILY ============
  openai: {
    gpt4Turbo: {
      id: 'gpt-4-turbo-preview',
      name: 'GPT-4 Turbo',
      contextWindow: 128000,
      costPer1kTokens: { input: 0.01, output: 0.03 },
      capabilities: ['vision', 'function_calling', 'json_mode'],
      temperature: 0.7,
      topP: 0.95,
      maxTokens: 4096
    },
    gpt4: {
      id: 'gpt-4',
      name: 'GPT-4',
      contextWindow: 8192,
      costPer1kTokens: { input: 0.03, output: 0.06 },
      capabilities: ['vision', 'function_calling'],
      temperature: 0.7,
      maxTokens: 2048
    },
    gpt35Turbo: {
      id: 'gpt-3.5-turbo',
      name: 'GPT-3.5 Turbo',
      contextWindow: 4096,
      costPer1kTokens: { input: 0.0005, output: 0.0015 },
      capabilities: ['function_calling'],
      temperature: 0.7,
      maxTokens: 2048
    }
  },

  // ============ ANTHROPIC CLAUDE ============
  anthropic: {
    claude3Opus: {
      id: 'claude-3-opus',
      name: 'Claude 3 Opus',
      contextWindow: 200000,
      costPer1kTokens: { input: 0.015, output: 0.075 },
      capabilities: ['vision', 'extended_thinking', 'function_calling'],
      temperature: 0.8,
      maxTokens: 4096
    },
    claude3Sonnet: {
      id: 'claude-3-sonnet',
      name: 'Claude 3 Sonnet',
      contextWindow: 200000,
      costPer1kTokens: { input: 0.003, output: 0.015 },
      capabilities: ['vision', 'function_calling'],
      temperature: 0.8,
      maxTokens: 2048
    }
  },

  // ============ OPEN SOURCE MODELS ============
  openSource: {
    llama2Chat: {
      id: 'llama-2-70b-chat',
      name: 'LLaMA 2 70B Chat',
      contextWindow: 4096,
      costPer1kTokens: { input: 0.001, output: 0.002 },
      capabilities: ['chat', 'function_calling'],
      temperature: 0.7,
      maxTokens: 2048,
      provider: 'together-ai'
    },
    mistral7b: {
      id: 'mistral-7b-instruct',
      name: 'Mistral 7B Instruct',
      contextWindow: 8192,
      costPer1kTokens: { input: 0.0002, output: 0.0006 },
      capabilities: ['chat', 'function_calling'],
      temperature: 0.7,
      maxTokens: 2048,
      provider: 'mistral-ai'
    }
  },

  // ============ SPECIALIZED MODELS ============
  specialized: {
    // Code Generation
    codeGeneration: {
      primary: 'gpt-4-turbo-preview',
      fallback: 'claude-3-sonnet',
      systemPrompt: `You are an expert code generation AI assistant. Your task is to:
1. Generate clean, production-ready code
2. Follow best practices and design patterns
3. Include comprehensive error handling
4. Write well-documented code with clear comments
5. Consider security and performance implications
6. Provide context and explanations for complex logic`,
      temperature: 0.3
    },

    // Content Generation
    contentGeneration: {
      primary: 'claude-3-opus',
      fallback: 'gpt-4-turbo-preview',
      systemPrompt: `You are a creative content generation AI. Produce:
1. High-quality, engaging content
2. Contextually appropriate tone and style
3. SEO-optimized text
4. Multiple perspectives and angles
5. Original ideas and insights`,
      temperature: 0.8
    },

    // Analysis & Reasoning
    analysis: {
      primary: 'claude-3-opus',
      fallback: 'gpt-4-turbo-preview',
      systemPrompt: `You are an advanced analytical AI. Perform:
1. Deep contextual analysis
2. Identify patterns and anomalies
3. Provide evidence-based insights
4. Consider multiple perspectives
5. Generate actionable recommendations`,
      temperature: 0.5
    },

    // Real-time Chat
    chat: {
      primary: 'gpt-3.5-turbo',
      fallback: 'claude-3-sonnet',
      systemPrompt: `You are a helpful AI assistant optimized for real-time conversation.
1. Respond naturally and conversationally
2. Remember context from the conversation
3. Ask clarifying questions when needed
4. Provide concise but complete answers`,
      temperature: 0.7
    }
  }
};

// ============ MODEL SELECTION STRATEGY ============
const selectBestModel = (task, constraints = {}) => {
  const { maxCost, minQuality, speed = 'balanced', contextSize } = constraints;

  const taskConfig = aiModels.specialized[task];
  if (!taskConfig) return aiModels.specialized.chat;

  // Cost optimization
  if (maxCost && maxCost < 0.005) {
    return aiModels.openSource.llama2Chat;
  }

  // Speed optimization (fast < balanced < quality)
  if (speed === 'fast') {
    return aiModels.openai.gpt35Turbo;
  } else if (speed === 'quality') {
    return taskConfig.primary;
  }

  return taskConfig.primary || taskConfig.fallback;
};

// ============ TOKEN COUNTING ============
const estimateTokens = (text) => {
  // Rough estimation: 1 token ≈ 4 characters
  return Math.ceil(text.length / 4);
};

const estimateCost = (model, inputTokens, outputTokens) => {
  let modelConfig;

  if (model.includes('gpt-4-turbo')) modelConfig = aiModels.openai.gpt4Turbo;
  else if (model.includes('gpt-4')) modelConfig = aiModels.openai.gpt4;
  else if (model.includes('gpt-3.5')) modelConfig = aiModels.openai.gpt35Turbo;
  else if (model.includes('claude-3-opus')) modelConfig = aiModels.anthropic.claude3Opus;
  else if (model.includes('claude-3-sonnet')) modelConfig = aiModels.anthropic.claude3Sonnet;
  else modelConfig = aiModels.openai.gpt35Turbo;

  const inputCost = (inputTokens / 1000) * modelConfig.costPer1kTokens.input;
  const outputCost = (outputTokens / 1000) * modelConfig.costPer1kTokens.output;

  return { inputCost, outputCost, totalCost: inputCost + outputCost };
};

module.exports = {
  aiModels,
  selectBestModel,
  estimateTokens,
  estimateCost
};
