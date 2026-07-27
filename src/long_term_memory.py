import os
from loguru import logger

class LongTermMemory:
    def __init__(self):
        self.memory_store = [] # Simulated for now, can be linked to ChromaDB/Pinecone

    def store_event(self, event_type, content):
        logger.info(f"💾 Storing {event_type} in Long-term Memory...")
        self.memory_store.append({"type": event_type, "content": content})

    def retrieve_context(self, query):
        # Basic keyword retrieval for now, upgradeable to semantic search
        relevant = [m['content'] for m in self.memory_store if any(word in m['content'] for word in query.split())]
        return "\n".join(relevant[-5:]) # Return last 5 relevant context pieces

memory_system = LongTermMemory()
