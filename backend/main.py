"""
Local Filesystem Agent — Main Application Entry Point.
"""
import os
import sys
import yaml
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from database.models import init_db
from tools.base import registry
from tools.file_tools import ALL_FILE_TOOLS
from tools.duplicate_tools import ALL_DUPLICATE_TOOLS
from tools.navigation_tools import ALL_NAVIGATION_TOOLS
from tools.search_tools import ALL_SEARCH_TOOLS
from tools.fileops_tools import ALL_FILEOPS_TOOLS
from permissions.policy import PolicyEngine
from llm.client import LLMClient
from memory.memory_store import MemoryStore
from api.routes import router, init_dependencies


# ─── Configuration ──────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def load_config():
    """Load YAML configuration."""
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


# ─── Lifespan ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    # ── Startup ──
    print("🚀 Starting Local Filesystem Agent...")

    # Initialize database
    await init_db()
    print("✅ Database initialized")

    # Register all tools
    all_tools = ALL_FILE_TOOLS + ALL_DUPLICATE_TOOLS + ALL_NAVIGATION_TOOLS + ALL_SEARCH_TOOLS + ALL_FILEOPS_TOOLS
    for tool in all_tools:
        registry.register(tool)
    print(f"✅ Registered {len(registry._tools)} tools")

    # Initialize LLM client
    llm_client = LLMClient(config_path=CONFIG_PATH)
    print(f"✅ LLM client ready ({llm_client.provider}: {llm_client.model})")

    # Initialize policy engine
    policy_engine = PolicyEngine(config_path=CONFIG_PATH)
    print(f"✅ Policy engine loaded ({len(policy_engine.allowed_paths)} allowed, {len(policy_engine.denied_paths)} denied)")

    # Initialize memory store
    memory_store = MemoryStore()
    print("✅ Memory store ready")

    # Wire up dependencies
    init_dependencies(llm_client, policy_engine, memory_store)
    print("✅ All systems operational\n")

    yield

    # ── Shutdown ──
    print("👋 Shutting down...")


# ─── App ────────────────────────────────────────────────
config = load_config()

app = FastAPI(
    title="Local Filesystem Agent",
    description="Natural language → Plan → Safe execution on files",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for frontend
server_config = config.get("server", {})
app.add_middleware(
    CORSMiddleware,
    allow_origins=server_config.get("cors_origins", ["http://localhost:3000"]),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)


# ─── Health check ───────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "Local Filesystem Agent"}


if __name__ == "__main__":
    import uvicorn
    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 8000)
    uvicorn.run("main:app", host=host, port=port, reload=True)
