import os
from collections.abc import AsyncIterable
from time import sleep

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.sse import EventSourceResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()


@app.get("/api/data")
async def root():
    return {"message": "Hello World!"}


app.mount("/assets", StaticFiles(directory="frontend/dist/assets"))


test_text: str = "A production-grade multi-agent research system built with Google ADK, MCP, and pgvector. Three specialist AI agents (Researcher, Critic, Synthesizer) collaborate via the Model Context Protocol to answer questions about MCP and ADK documentation — cited, grounded, and streamed live to a SolidJS dashboard."


@app.get("/api/chat", response_class=EventSourceResponse)
async def sse_stream() -> AsyncIterable[str]:
    chunks = test_text.split(" ")
    for chunk in chunks:
        sleep(0.2)
        yield chunk


@app.api_route("/{path_name:path}", methods=["GET"])
async def catch_all(path_name: str):
    dist_dir = "frontend/dist"
    file_path = os.path.join(dist_dir, path_name)

    if os.path.isfile(file_path):
        return FileResponse(file_path)

    return FileResponse(os.path.join(dist_dir, "index.html"))
