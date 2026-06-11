# Streaming Debug Guide

How to diagnose missing or invisible content in the agent SSE stream.
Canonically applied to: **reasoning/thinking tokens not reaching the frontend.**

## The chain

Everything that appears in a chat message passes through these layers:

```
API response (raw JSON)
  │
  ▼
langchain_openai._convert_delta_to_message_chunk    ← Patch point 1 (delta)
  │                                                     Patch point 2 (choice)
  ▼
AIMessageChunk (LangChain internal)
  │
  ▼
agent.astream(stream_mode="messages")                ← Observation point
  │
  ▼
StreamEventHandler.observe(chunk, metadata)          ← SSE event builder
  │
  ▼
SSE: data: {"type":"TEXT_MESSAGE_CONTENT",...}
     data: {"type":"REASONING_MESSAGE_CONTENT",...}  ← Wire format
  │
  ▼
@tanstack/ai StreamProcessor.processChunk()          ← ThinkingPart or TextPart
  │
  ▼
MessagePartRenderer (type === "thinking"?)           ← Frontend renderer
```

## Feedback loop (the skill)

Before any hypothesis, build a **fast, deterministic pass/fail signal**.
For streaming bugs the canonical loop is:

```bash
curl -s -N -X POST "http://localhost:8000/api/chat/eu-ai-act" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Hello","id":"u1"}],"threadId":"t","runId":"r"}' \
  2>&1 | grep 'REASONING_MESSAGE\|TEXT_MESSAGE\|TOOL_CALL'
```

*Filtering* for expected event types tells you immediately if the pipeline
emits them. *Not filtering* (full output) shows you the raw event stream
for pattern-matching.

## Diagnosis phases

### Phase 1 — Is the SSRE stream correct?

Run the curl loop. If you see `REASONING_MESSAGE_*` events → the backend is
working. The bug is in the frontend (stream processor or renderer).

If you see only `TEXT_MESSAGE_*` events → the backend is not emitting
reasoning events. Proceed to Phase 2.

### Phase 2 — Are the AIMessageChunks carrying reasoning?

Add a file-log at the observation point in `backend/agents/pipeline.py`:

```python
async for chunk, metadata in agent.astream(...):
    if isinstance(chunk, BaseMessage):
        with open("/tmp/debug_stream.log", "a") as _f:
            _f.write(
                f"[DBG] type={type(chunk).__name__} "
                f"content={str(chunk.content)[:120]!r} "
                f"additional_kwargs={dict(getattr(chunk, 'additional_kwargs', {}))} "
                f"tool_call_chunks={getattr(chunk, 'tool_call_chunks', 'N/A')}\n"
            )
        handler.observe(chunk, metadata)
```

Restart the server, make one curl request, then:

```bash
grep -v "additional_kwargs={}" /tmp/debug_stream.log | head -20
```

If chunks have `additional_kwargs={'reasoning_content': '...'}` → the
patch is working, reasoning reaches the handler. The bug is in the handler or
event encoding.

If chunks have `additional_kwargs={}` even for reasoning tokens → the
patch is not capturing the reasoning field. Proceed to Phase 3.

### Phase 3 — Is the monkey-patch being called?

Instrument the patch in `backend/agents/__init__.py`:

```python
def _patched_convert_delta(_dict, default_class):
    with open("/tmp/debug_patch.log", "a") as _f:
        _f.write(
            f"[DBG] patch=convert_delta keys={list(_dict.keys())} "
            f"reasoning_content={_dict.get('reasoning_content')!r} "
            f"reasoning={_dict.get('reasoning')!r} "
            f"reasoning_details={_dict.get('reasoning_details')!r}\n"
        )
    # ... rest of patch
```

Restart and re-run the curl loop.

If the log shows `reasoning='The user...'` but the field check in the patch
uses `_dict.get("reasoning_content")` → you found the gap. The API sends
the field under a different key than the patch checks.

### Phase 4 — Known field-name variations

| Field name             | Location in chunk JSON | Example providers          |
|------------------------|------------------------|----------------------------|
| `reasoning_content`    | `choices[0]`           | DeepSeek (choice level)    |
| `reasoning`            | `choices[0]["delta"]`  | OpenAI o-series, Gemini    |
| `reasoning_details`    | `choices[0]["delta"]`  | Same, structured array     |

All three are normalised to `AIMessageChunk.additional_kwargs["reasoning_content"]`
by the patch in `backend/agents/__init__.py`.

## Instrumentation cleanup

Tag every debug log with a unique prefix (e.g. `[DBG]`). Before committing,
remove all tagged logs:

```bash
grep -rn '\[DBG\]' backend/agents/
```
