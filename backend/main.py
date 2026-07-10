"""
Local Filesystem Agent — Main Application Entry Point.
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from api.routes import init_dependencies, router
from database.models import init_db
from llm.client import LLMClient
from memory.memory_store import MemoryStore
from permissions.policy import PolicyEngine
from tools.base import registry
from tools.document_understanding_tools import ALL_DOCUMENT_UNDERSTANDING_TOOLS
from tools.duplicate_tools import ALL_DUPLICATE_TOOLS
from tools.exif_tools import ALL_EXIF_TOOLS
from tools.extraction_tools import ALL_EXTRACTION_TOOLS
from tools.file_tools import ALL_FILE_TOOLS
from tools.fileops_tools import ALL_FILEOPS_TOOLS
from tools.git_tools import ALL_GIT_TOOLS
from tools.image_understanding_tools import ALL_IMAGE_UNDERSTANDING_TOOLS
from tools.index_tools import ALL_INDEX_TOOLS
from tools.navigation_tools import ALL_NAVIGATION_TOOLS
from tools.search_tools import ALL_SEARCH_TOOLS
from tools.security_tools import ALL_SECURITY_TOOLS
from tools.system_tools import ALL_SYSTEM_TOOLS
from tools.terminal_tools import ALL_TERMINAL_TOOLS
from tools.web_tools import ALL_WEB_TOOLS
# Phase 2 tools
from tools.desktop_tools import ALL_DESKTOP_TOOLS
from tools.plugin_tools import ALL_PLUGIN_TOOLS
# Phase 3 tools
from tools.voice_tools import ALL_VOICE_TOOLS
from indexing.index_store import IndexStore
from indexing.indexer import IndexerService
# Phase 2 services
from scheduler.scheduler import scheduler_service
from knowledge.kb import init_kb_db, kb
from cache.cache import metadata_cache, search_cache

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
    all_tools = (
        ALL_FILE_TOOLS
        + ALL_DUPLICATE_TOOLS
        + ALL_NAVIGATION_TOOLS
        + ALL_SEARCH_TOOLS
        + ALL_FILEOPS_TOOLS
        + ALL_EXTRACTION_TOOLS
        + ALL_DOCUMENT_UNDERSTANDING_TOOLS
        + ALL_IMAGE_UNDERSTANDING_TOOLS
        + ALL_SECURITY_TOOLS
        + ALL_GIT_TOOLS
        + ALL_TERMINAL_TOOLS
        + ALL_EXIF_TOOLS
        + ALL_SYSTEM_TOOLS
        + ALL_INDEX_TOOLS
        + ALL_WEB_TOOLS
        # Phase 2
        + ALL_DESKTOP_TOOLS
        + ALL_PLUGIN_TOOLS
        # Phase 3: Voice & Audio Intelligence
        + ALL_VOICE_TOOLS
    )
    for tool in all_tools:
        registry.register(tool)
    print(f"✅ Registered {len(registry._tools)} tools")

    # Initialize LLM client
    llm_client = LLMClient(config_path=CONFIG_PATH)
    print(f"✅ LLM client ready ({llm_client.provider}: {llm_client.model})")

    # Inject LLM client into tools that need it
    semantic_tool = registry.get("semantic_search")
    if semantic_tool:
        semantic_tool.llm_client = llm_client
    organize_ai_tool = registry.get("organize_by_ai")
    if organize_ai_tool:
        organize_ai_tool.llm_client = llm_client

    # Document understanding tools
    for tool_name in [
        "summarize_document",
        "explain_document",
        "compare_documents",
        "find_similar_documents",
        "summarize_folder",
    ]:
        tool = registry.get(tool_name)
        if tool:
            tool.llm_client = llm_client

    # Image understanding tools
    for tool_name in ["describe_image", "search_images_by_description"]:
        tool = registry.get(tool_name)
        if tool:
            tool.llm_client = llm_client

    # Initialize policy engine
    policy_engine = PolicyEngine(config_path=CONFIG_PATH)
    print(
        f"✅ Policy engine loaded ({len(policy_engine.allowed_paths)} allowed, {len(policy_engine.denied_paths)} denied)"
    )

    # Initialize memory store
    memory_store = MemoryStore()
    print("✅ Memory store ready")

    # ── Filesystem search index ──
    index_store = IndexStore()
    await index_store.init()
    indexer = IndexerService(index_store, policy_engine=policy_engine)
    indexer.default_roots = policy_engine.allowed_paths or [os.path.expanduser("~")]

    indexed_search_tool = registry.get("indexed_search")
    if indexed_search_tool:
        indexed_search_tool.store = index_store
    rebuild_index_tool = registry.get("rebuild_index")
    if rebuild_index_tool:
        rebuild_index_tool.indexer = indexer
    index_status_tool = registry.get("index_status")
    if index_status_tool:
        index_status_tool.indexer = indexer
        index_status_tool.store = index_store

    # Kick off the initial index build in the background (non-blocking)
    asyncio.create_task(indexer.build_index(indexer.default_roots))
    print(f"✅ Filesystem index building in background ({len(indexer.default_roots)} root(s))")

    # Enable real-time incremental updates if 'watchdog' is installed
    loop = asyncio.get_event_loop()
    if indexer.start_watching(indexer.default_roots, loop):
        print("✅ Live filesystem watch enabled")
    else:
        print("⚠️  Live filesystem watch disabled (install 'watchdog' to enable)")

    # Wire up dependencies
    init_dependencies(llm_client, policy_engine, memory_store)

    # ── Phase 2: Knowledge Base ──
    await init_kb_db()
    print("✅ Knowledge Base initialized")

    # ── Phase 2: Scheduler ──
    await scheduler_service.start()
    print("✅ Task scheduler started")

    print("✅ All systems operational\n")

    yield

    # ── Shutdown ──
    scheduler_service.stop()
    indexer.stop_watching()
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
