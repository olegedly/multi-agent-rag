from collections.abc import AsyncIterable
from time import sleep

from fastapi import FastAPI
from fastapi.sse import EventSourceResponse

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World!"}


test_text: str = "A production-grade multi-agent research system built with Google ADK, MCP, and pgvector. Three specialist AI agents (Researcher, Critic, Synthesizer) collaborate via the Model Context Protocol to answer questions about MCP and ADK documentation — cited, grounded, and streamed live to a SolidJS dashboard."


@app.get("/api/chat", response_class=EventSourceResponse)
async def sse_stream() -> AsyncIterable[str]:
    chunks = test_text.split(" ")
    for chunk in chunks:
        sleep(0.2)
        yield chunk
