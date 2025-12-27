# secure_hospital_ai/chat/views.py

import json
import asyncio
from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from frontend.llm_handler import StreamingLLMAgent

def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

@csrf_exempt
async def chat_message_sse(request):
    if request.method != "POST":
        return StreamingHttpResponse("Only POST allowed", status=405)

    body = json.loads(request.body.decode())
    user_message = body["message"]
    agent = StreamingLLMAgent(request.user, request)

    async def stream():
        yield sse("start", {"status": "started"})

        async for chunk in agent.stream_chat(user_message):
            yield sse("chunk", json.loads(chunk))

        yield sse("end", {"status": "complete"})

    response = StreamingHttpResponse(stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
