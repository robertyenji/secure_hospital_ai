# OpenAI API Update Fix

## Problem
The old OpenAI Python library (< 1.0.0) API was deprecated. Your code was trying to use:
```python
openai.api_key = "..."
openai.ChatCompletion.create(...)
openai.Model.list()
```

This causes errors like:
```
You tried to access openai.Model, but this is no longer supported in openai>=1.0.0
Internal Server Error: /api/chat/message/
[11/Nov/2025 13:30:08] "POST /api/chat/message/ HTTP/1.1" 500 79
```

## Solution
Updated `frontend/llm_handler.py` to use the new OpenAI Python Client (1.0.0+) API:

### Changes Made

#### 1. **Import Changes** (Line 18)
**Old:**
```python
import openai
```

**New:**
```python
from openai import OpenAI, APIConnectionError, APIStatusError, APITimeoutError
```

#### 2. **Client Initialization** (Lines 31-32)
**Old:**
```python
openai.api_key = cls.API_KEY
openai.Model.list()  # This doesn't work anymore
```

**New:**
```python
global _openai_client
if _openai_client is None:
    _openai_client = OpenAI(api_key=LLMConfig.API_KEY)
_openai_client.models.list()  # New API endpoint
```

#### 3. **Chat Completion Calls** (Line 371)
**Old:**
```python
response_stream = openai.ChatCompletion.create(
    api_key=LLMConfig.API_KEY,
    model=LLMConfig.MODEL,
    messages=messages,
    tools=tools,
    tool_choice="auto",
    stream=True,
)
```

**New:**
```python
response_stream = _openai_client.chat.completions.create(
    model=LLMConfig.MODEL,
    messages=messages,
    tools=tools,
    tool_choice="auto",
    stream=True,
)
```

#### 4. **Response Parsing** (Lines 397-410)
**Old:**
```python
for chunk in response_stream:
    choices = chunk.get("choices", [])
    delta = choices[0].get("delta", {})
    
    if "content" in delta and delta["content"]:
        content = delta["content"]
```

**New:**
```python
for chunk in response_stream:
    choices = chunk.choices
    delta = choices[0].delta
    
    if delta.content:
        content = delta.content
```

The new API returns objects instead of dictionaries, making the code cleaner.

## Installation

Before testing, install the latest OpenAI package:

```bash
pip install --upgrade openai
```

Or to be specific:
```bash
pip install 'openai>=1.0.0'
```

## Testing

After installation, the chat endpoints should work:

1. **Create a chat session:** Click "+ New Chat"
2. **Send a message:** Type a question and click Send
3. **Expected response:** LLM responds with proper streaming

## Verification

If you get 401 errors on `/api/chat/session/`, that's a JWT authentication issue, not the OpenAI fix.

If you get 500 errors on `/api/chat/message/`, check:
- ✅ OpenAI package is installed: `pip list | grep openai`
- ✅ LLM_API_KEY is set in `.env` file
- ✅ Django server has been restarted after the code changes

## API Changes Summary

| Feature | Old API | New API |
|---------|---------|---------|
| **Import** | `import openai` | `from openai import OpenAI` |
| **Auth** | `openai.api_key = key` | `OpenAI(api_key=key)` |
| **Chat Call** | `openai.ChatCompletion.create()` | `client.chat.completions.create()` |
| **Model List** | `openai.Model.list()` | `client.models.list()` |
| **Response Type** | Dict (`.get()`) | Object (`.attribute`) |
| **Streaming** | Dict chunks | Object chunks |

## References

- [OpenAI Python GitHub](https://github.com/openai/openai-python)
- [Migration Guide](https://github.com/openai/openai-python/discussions/742)
- [API Reference](https://platform.openai.com/docs/api-reference)

---

**Status:** ✅ Code updated and ready for testing

**Next Step:** 
1. Run: `pip install --upgrade openai`
2. Restart Django: `python manage.py runserver`
3. Try the chat again
