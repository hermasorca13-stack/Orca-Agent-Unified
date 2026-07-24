/**
 * Knowledge Base Service - Advanced Context Management
 * RAG (Retrieval Augmented Generation) Implementation
 */

const VectorStore = require('./vector-store');
const { logger } = require('../utils/logger');

class KnowledgeBase {
  constructor() {
    this.vectorStore = new VectorStore();
    this.metadata = new Map();
  }

  // ============ INGEST DOCUMENTS ============
  async ingestDocument(doc) {
    try {
      logger.info(`📚 Ingesting document: ${doc.title}`);

      // Split document into chunks
      const chunks = this._chunkDocument(doc.content, 500); // 500 char chunks

      // Add chunks to vector store
      for (let i = 0; i < chunks.length; i++) {
        await this.vectorStore.add({
          content: chunks[i],
          metadata: {
            docId: doc.id,
            docTitle: doc.title,
            chunkIndex: i,
            source: doc.source,
            timestamp: new Date()
          }
        });
      }

      this.metadata.set(doc.id, {
        title: doc.title,
        source: doc.source,
        chunkCount: chunks.length,
        ingestedAt: new Date()
      });

      logger.info(`✅ Document ingested with ${chunks.length} chunks`);
      return { docId: doc.id, chunks: chunks.length };
    } catch (error) {
      logger.error(`❌ Document ingestion failed: ${error.message}`);
      throw error;
    }
  }

  // ============ QUERY WITH RAG ============
  async queryWithRAG(question, topK = 5) {
    try {
      logger.info(`🔍 RAG Query: ${question}`);

      // Search relevant documents
      const relevantChunks = await this.vectorStore.search(question, topK);

      // Build context
      const context = relevantChunks
        .map((chunk, idx) => `\n[Source ${idx + 1}]: ${chunk.metadata.docTitle}\n${chunk.metadata}\n${chunk.values.slice(0, 50).join(', ')}...`)
        .join('\n');

      return {
        question,
        context,
        sources: relevantChunks.map(c => ({
          docTitle: c.metadata.docTitle,
          source: c.metadata.source,
          relevance: c.score
        }))
      };
    } catch (error) {
      logger.error(`❌ RAG query failed: ${error.message}`);
      throw error;
    }
  }

  // ============ BATCH INGEST ============
  async batchIngest(documents) {
    const results = [];
    for (const doc of documents) {
      const result = await this.ingestDocument(doc);
      results.push(result);
    }
    return results;
  }

  // ============ GET KNOWLEDGE BASE STATS ============
  getStats() {
    return {
      totalDocuments: this.metadata.size,
      documents: Array.from(this.metadata.entries()).map(([id, meta]) => ({
        id,
        ...meta
      }))
    };
  }

  // ============ PRIVATE METHODS ============
  _chunkDocument(content, chunkSize = 500) {
    const chunks = [];
    for (let i = 0; i < content.length; i += chunkSize) {
      chunks.push(content.substring(i, i + chunkSize));
    }
    return chunks;
  }
}

module.exports = KnowledgeBase;
