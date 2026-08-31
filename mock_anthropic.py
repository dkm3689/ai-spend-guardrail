"""
Local mock of the Anthropic API — returns realistic fake responses.
Run: python3 mock_anthropic.py
Runs on port 8001.
"""
import time
import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import json

app = FastAPI(title="Mock Anthropic API")

FAKE_REPLY = "Hello! I'm a mock Claude response. The proxy is working correctly."

MODEL_PRICING = {
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "claude-haiku-4-5":          (0.80, 4.0),
    "claude-sonnet-5":           (3.0,  15.0),
    "claude-sonnet-4-5":         (3.0,  15.0),
    "claude-opus-4-8":           (15.0, 75.0),
}


@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    model = body.get("model", "claude-haiku-4-5-20251001")
    is_stream = body.get("stream", False)

    input_tokens = sum(len(m["content"].split()) * 2 for m in body.get("messages", []))
    output_tokens = len(FAKE_REPLY.split()) * 2
    msg_id = f"msg_{uuid.uuid4().hex[:24]}"

    if is_stream:
        return StreamingResponse(
            _stream(msg_id, model, input_tokens, output_tokens),
            media_type="text/event-stream",
        )

    return JSONResponse({
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": FAKE_REPLY}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    })


async def _stream(msg_id, model, input_tokens, output_tokens):
    def event(data): return f"data: {json.dumps(data)}\n\n".encode()

    yield event({"type": "message_start", "message": {
        "id": msg_id, "type": "message", "role": "assistant",
        "model": model, "content": [],
        "usage": {"input_tokens": input_tokens, "output_tokens": 0},
    }})
    yield event({"type": "content_block_start", "index": 0,
                 "content_block": {"type": "text", "text": ""}})

    for word in FAKE_REPLY.split():
        yield event({"type": "content_block_delta", "index": 0,
                     "delta": {"type": "text_delta", "text": word + " "}})

    yield event({"type": "content_block_stop", "index": 0})
    yield event({"type": "message_delta",
                 "delta": {"stop_reason": "end_turn"},
                 "usage": {"output_tokens": output_tokens}})
    yield event({"type": "message_stop"})


@app.get("/health")
def health():
    return {"status": "ok", "mock": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
