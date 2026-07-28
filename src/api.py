"""FastAPI application - REST API for Orca Agent"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
from loguru import logger

# Ensure project root is in path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import OrcaAgent
# Optional: routes.telegram is from a sibling FastAPI project. If unavailable (e.g. this
# repo only carries the Orca Agent core), the Orca API still boots — we just skip that router.
try:
    from routes.telegram import router as telegram_router  # type: ignore
    _HAS_TELEGRAM_ROUTER = True
except Exception as _e:
    logger.debug(f"src.api: telegram router not available ({_e}) — running without it")
    telegram_router = None
    _HAS_TELEGRAM_ROUTER = False

# Initialize FastAPI app
app = FastAPI(
    title="���� Orca Agent",
    description="Advanced Multi-Tier AI Framework",
    version="1.0.0"
)

# Initialize agent
agent = OrcaAgent()

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize agent on startup"""
    logger.info("🚀 Starting Orca Agent API...")
    await agent.initialize()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("⛔ Shutting down Orca Agent API...")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return await agent.health_check()


@app.get("/api/status")
async def get_status():
    """Get current agent status"""
    return {
        "status": "operational",
        "version": "1.0.0",
        "initialized": agent.initialized
    }


@app.post("/api/task/process")
async def process_task(task: str):
    """Process a task through the agent"""
    try:
        result = await agent.process_task(task)
        return result
    except Exception as e:
        logger.error(f"Task processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat(user_id: str, message: str, options: dict = None):
    """Process a chat message through the agent"""
    try:
        result = await agent.chat(user_id, message, options)
        return result
    except Exception as e:
        logger.error(f"Chat processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/github/webhook")
async def github_webhook(request: dict):
    """GitHub webhook receiver"""
    logger.info(f"📨 Received GitHub webhook: {request.get('action', 'unknown')}")
    return {"status": "received"}


@app.post("/api/manus/sync")
async def manus_sync():
    """Trigger manual Manus sync"""
    logger.info("🔄 Triggering Manus sync...")
    return {"status": "syncing"}


# Include Telegram routes (if available)
if _HAS_TELEGRAM_ROUTER and telegram_router is not None:
    app.include_router(telegram_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)