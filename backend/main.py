from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint
from fastapi import FastAPI
from google.adk.agents import Agent

from backend.config import settings
from backend.llm.adk_adapter import AdkLlmAdapter
from backend.llm.factory import create_llm_client

app = FastAPI(title=settings.app_name)


# ---------------------------------------------------------------------------
# LLM — injected via environment, not hardcoded
# ---------------------------------------------------------------------------

# DI seam: reassign get_llm_client in tests to inject a fake client
get_llm_client = create_llm_client

llm_client = get_llm_client()
llm_model = AdkLlmAdapter(llm_client)

root_agent = Agent(
    name="rag_assistant",
    model=llm_model,
    instruction=(
        "You are a helpful research assistant. Answer questions clearly and concisely."
    ),
)

adk_agent = ADKAgent(
    adk_agent=root_agent,
    app_name=settings.app_name,
    user_id="dev",
)

# Mounts POST /api/chat as AG-UI endpoint, plus GET /capabilities and POST /agents/state
add_adk_fastapi_endpoint(app, adk_agent, path="/api/chat")


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"app": settings.app_name, "status": "ok"}
