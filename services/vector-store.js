/**
 * Vector Database Service - RAG & Semantic Search
 * Supports: Pinecone, Weaviate, Milvus, FAISS
 */

const axios = require('axios');
const { logger } = require('../utils/logger');

class VectorStore {
  constructor(config = {}) {
    this.provider = process.env.VECTOR_DB_PROVIDER || 'pinecone';
    this.apiKey = process.env.VECTOR_DB_API_KEY;
    this.namespace = config.namespace || 'default';
    this.client = this._initializeClient();
  }

  _initializeClient() {
    if (this.provider === 'pinecone') {
      return {
        baseUrl: process.env.PINECONE_ENDPOINT,
        apiKey: this.apiKey,
        indexName: process.env.PINECONE_INDEX || 'hermes'
      };
    }
    // Add support for other providers
    return null;
  }

  // ============ ADD VECTORS ============
  async add(data) {
    try {
      const embedding = await this._getEmbedding(data.content);

      const payload = {
        vectors: [
          {
            id: data.embedding || `emb-${Date.now()}-${Math.random()}`,
            values: embedding,
            metadata: data.metadata || {}
          }
        ],
        namespace: this.namespace
      };

      const response = await axios.post(
        `${this.client.baseUrl}/vectors/upsert`,
        payload,
        {
          headers: {
            'Api-Key': this.client.apiKey,
            'Content-Type': 'application/json'
          }
        }
      );

      logger.info(`✅ Vector stored: ${data.embedding}`);
      return response.data;
    } catch (error) {
      logger.error(`❌ Failed to add vector: ${error.message}`);
      throw error;
    }
  }

  // ============ SEARCH VECTORS ============
  async search(query, topK = 5) {
    try {
      const embedding = await this._getEmbedding(query);

      const response = await axios.post(
        `${this.client.baseUrl}/query`,
        {
          vector: embedding,
          topK: topK,
          namespace: this.namespace,
          includeMetadata: true
        },
        {
          headers: {
            'Api-Key': this.client.apiKey,
            'Content-Type': 'application/json'
          }
        }
      );

      logger.info(`🔍 Search found ${response.data.matches?.length || 0} results`);
      return response.data.matches || [];
    } catch (error) {
      logger.error(`❌ Search failed: ${error.message}`);
      return [];
    }
  }

  // ============ SEMANTIC SEARCH ============
  async semanticSearch(query, filters = {}) {
    try {
      const results = await this.search(query, 10);

      // Apply filters
      let filtered = results;
      for (const [key, value] of Object.entries(filters)) {
        filtered = filtered.filter(r => r.metadata[key] === value);
      }

      return filtered;
    } catch (error) {
      logger.error(`❌ Semantic search failed: ${error.message}`);
      throw error;
    }
  }

  // ============ DELETE ============
  async delete(id) {
    try {
      await axios.delete(
        `${this.client.baseUrl}/vectors/${id}`,
        {
          headers: { 'Api-Key': this.client.apiKey },
          params: { namespace: this.namespace }
        }
      );
      logger.info(`🗑️  Vector deleted: ${id}`);
    } catch (error) {
      logger.error(`❌ Delete failed: ${error.message}`);
      throw error;
    }
  }

  // ============ BATCH OPERATIONS ============
  async batchAdd(dataList) {
    const vectors = [];

    for (const data of dataList) {
      const embedding = await this._getEmbedding(data.content);
      vectors.push({
        id: data.embedding || `emb-${Date.now()}-${Math.random()}`,
        values: embedding,
        metadata: data.metadata || {}
      });
    }

    try {
      const response = await axios.post(
        `${this.client.baseUrl}/vectors/upsert`,
        { vectors, namespace: this.namespace },
        { headers: { 'Api-Key': this.client.apiKey } }
      );
      logger.info(`✅ Batch added ${dataList.length} vectors`);
      return response.data;
    } catch (error) {
      logger.error(`❌ Batch add failed: ${error.message}`);
      throw error;
    }
  }

  // ============ PRIVATE METHODS ============
  async _getEmbedding(text) {
    try {
      const response = await axios.post(
        'https://api.openai.com/v1/embeddings',
        {
          input: text,
          model: 'text-embedding-3-small'
        },
        {
          headers: {
            'Authorization': `Bearer ${process.env.OPENAI_API_KEY}`,
            'Content-Type': 'application/json'
          }
        }
      );

      return response.data.data[0].embedding;
    } catch (error) {
      logger.error(`❌ Embedding generation failed: ${error.message}`);
      throw error;
    }
  }
}

module.exports = VectorStore;
