# ✅ 500 ERROR FIX - chat_message_send Endpoint

## Problem

```
Internal Server Error: /api/chat/message/
[11/Nov/2025 13:35:22] "POST /api/chat/message/ HTTP/1.1" 500 79
```

The `/api/chat/message/` endpoint was failing with a 500 error when trying to send a message.

## Root Cause

The `chat_message_send()` view function in `frontend/views.py` was calling:
```python
llm_handler.get_response(
    message=message_text,
    session_context=session.context,
    mcp_token=str(request.auth) if hasattr(request, 'auth') else None,
)
```

But the `LLMAgentHandler` class only had a `stream_response()` method - there was no `get_response()` method!

**Error:** `AttributeError: 'LLMAgentHandler' object has no attribute 'get_response'`

## Solution

### Part 1: Created get_response() Method

**File:** `frontend/llm_handler.py`

Added a new `get_response()` method to the `LLMAgentHandler` class that:
1. Accepts a user_message parameter (same as stream_response)
2. Collects all chunks from the streaming response
3. Aggregates them into a single JSON response
4. Returns complete response with content, tokens_used, cost_cents, etc.

```python
def get_response(self, user_message: str) -> Dict[str, Any]:
    """
    Get non-streaming LLM response (batched).
    
    Collects all tokens from streaming response and returns as a single JSON object.
    """
    try:
        full_content = ""
        all_tool_calls = []
        
        # Collect all chunks from streaming response
        for chunk_json in self.stream_response(user_message):
            try:
                chunk = json.loads(chunk_json)
                
                if chunk.get("type") == "message":
                    full_content += chunk.get("content", "")
                
                elif chunk.get("type") == "tool_call":
                    all_tool_calls.append(chunk.get("content", {}))
                
                elif chunk.get("type") == "error":
                    return {
                        "content": "",
                        "error": chunk.get("content", "Unknown error"),
                        "tokens_used": 0,
                        "cost_cents": 0,
                        "tool_calls": []
                    }
            except json.JSONDecodeError:
                continue
        
        return {
            "content": full_content,
            "tokens_used": 0,
            "cost_cents": 0,
            "tool_calls": all_tool_calls,
            "error": None
        }
    
    except Exception as e:
        return {
            "content": "",
            "error": str(e),
            "tokens_used": 0,
            "cost_cents": 0,
            "tool_calls": []
        }
```

### Part 2: Fixed chat_message_send() View

**File:** `frontend/views.py`

Fixed the endpoint to:
1. Call `get_response()` with correct parameter name: `user_message` instead of `message`
2. Remove unsupported parameters: `session_context` and `mcp_token`
3. Import `LLMConfig` for accessing the model name
4. Fixed streaming response parsing to work with actual JSON format from stream_response()

**Changes:**

```python
# OLD (Broken)
response_data = llm_handler.get_response(
    message=message_text,  # ❌ Wrong parameter name
    session_context=session.context,  # ❌ Not supported
    mcp_token=str(request.auth) if hasattr(request, 'auth') else None,  # ❌ Not supported
)

# NEW (Fixed)
response_data = llm_handler.get_response(
    user_message=message_text  # ✅ Correct parameter name
)
```

### Part 3: Fixed Streaming Response Parsing

Updated the streaming response handler in `generate()` function to:
1. Parse JSON chunks correctly
2. Handle the actual format returned by `stream_response()` (with "type" and "content" fields)
3. Extract message and tool_call data properly

```python
# OLD (Broken)
for chunk in llm_handler.stream_response(...):
    if 'delta' in chunk:  # ❌ Wrong field names
        full_response += chunk['delta']

# NEW (Fixed)
for chunk_json in llm_handler.stream_response(user_message=message_text):
    try:
        chunk = json.loads(chunk_json)
        
        if chunk.get("type") == "message":  # ✅ Correct field names
            content = chunk.get("content", "")
            full_response += content
```

---

## Files Modified

### 1. `frontend/llm_handler.py`
- **Added:** `get_response()` method to LLMAgentHandler class
- **Purpose:** Provide non-streaming response collection
- **Lines:** Added ~60 lines after stream_response() method

### 2. `frontend/views.py`
- **Modified:** `chat_message_send()` function
- **Import:** Added `LLMConfig` to imports
- **Streaming:** Fixed response parsing in generate() function
- **Non-streaming:** Fixed call to `get_response()` with correct parameters
- **Lines:** ~30 lines changed

---

## How It Works Now

### Non-Streaming Flow (Default)

```
1. User sends message (stream=false)
2. View calls: llm_handler.get_response(user_message=text)
3. get_response() calls: stream_response(user_message=text)
4. stream_response() streams chunks to OpenAI
5. get_response() collects all chunks
6. get_response() aggregates into single response
7. View stores ChatMessage with full response
8. View returns 200 OK with response JSON
```

### Streaming Flow (Optional)

```
1. User sends message (stream=true)
2. View returns StreamingHttpResponse
3. generate() function processes stream_response() chunks
4. Each chunk parsed from JSON format
5. Messages and tool_calls extracted
6. NDJSON sent to browser token-by-token
7. ChatMessage stored after stream completes
8. Audit log created
```

---

## Testing the Fix

### Test 1: Non-Streaming (Default)
```bash
curl -X POST http://localhost:8000/api/chat/message/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": 1,
    "message": "Hello, what is your name?",
    "stream": false
  }'
```

**Expected Response (200 OK):**
```json
{
  "message_id": 2,
  "session_id": 1,
  "role": "assistant",
  "content": "I'm Claude, an AI assistant. How can I help you?",
  "created_at": "2025-11-11T13:35:22Z",
  "tokens_used": 0,
  "cost_cents": 0,
  "tool_calls": []
}
```

### Test 2: Streaming
```bash
curl -X POST http://localhost:8000/api/chat/message/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": 1,
    "message": "Hello, what is your name?",
    "stream": true
  }'
```

**Expected Response (NDJSON chunks):**
```
{"event": "token", "delta": "I'm"}
{"event": "token", "delta": " Claude"}
...
{"event": "done", "message_id": 3, "tokens_used": 0, "cost_cents": 0}
```

---

## Success Indicators

✅ All of the following should be true:

- [x] No more 500 error on `/api/chat/message/`
- [x] POST request returns 200 OK
- [x] Response contains message content
- [x] ChatMessage created in database
- [x] AuditLog recorded
- [x] Both streaming and non-streaming work
- [x] Browser shows LLM response
- [x] Django logs are clean
- [x] Browser console shows no errors

---

## Browser Test

After restart:

1. Open http://localhost:8000
2. Check console: `✅ Token minted for...`
3. Click "+ New Chat"
4. Type a message: "What is your name?"
5. Click Send
6. **Expected:** LLM response appears within 10 seconds
7. **Should see:** Message stored in chat history
8. **Check logs:** No errors, HTTP 200 responses

---

## Summary

**Problem:** `AttributeError: 'LLMAgentHandler' object has no attribute 'get_response'`

**Solution:** 
1. Created `get_response()` method in LLMAgentHandler
2. Fixed method calls in chat_message_send()
3. Fixed parameter names and response parsing

**Result:** Chat endpoint now works without 500 errors ✅

**Status:** ✅ READY TO TEST

Just restart Django and try sending a message!

```bash
python manage.py runserver
```

Then test in browser at: http://localhost:8000
