# Detailed Fix Documentation

## Summary of Changes

Two main issues were fixed:
1. **OpenAI API Deprecation** - Old `openai.ChatCompletion.create()` no longer works
2. **JWT Authentication** - Chat API endpoints weren't receiving authentication tokens

---

## File 1: `frontend/llm_handler.py`

### Issue: Using Deprecated OpenAI API

The file was using the old OpenAI Python library (< 1.0.0) syntax which is no longer supported.

### Fixes Applied

#### Fix 1.1: Import Statement (Line 18)

**Before:**
```python
import openai
```

**After:**
```python
from openai import OpenAI, APIConnectionError, APIStatusError, APITimeoutError
```

**Reason:** The new library exports classes and exceptions instead of a module-level API.

---

#### Fix 1.2: Global Client Initialization (Line 32)

**Added:**
```python
_openai_client = None
```

**Reason:** Need to maintain a single client instance throughout the module.

---

#### Fix 1.3: LLMConfig.validate() Method (Lines 62-77)

**Before:**
```python
@classmethod
def validate(cls):
    if not cls.API_KEY:
        logger.warning("LLM_API_KEY not configured - LLM features disabled")
        return False
    
    try:
        if cls.PROVIDER == "openai":
            openai.api_key = cls.API_KEY
            openai.Model.list()  # ❌ DEPRECATED
    except Exception as e:
        logger.error(f"LLM configuration invalid: {e}")
        return False
    
    logger.info(f"LLM configured: {cls.PROVIDER} / {cls.MODEL}")
    return True
```

**After:**
```python
@classmethod
def validate(cls):
    """Validate configuration on startup"""
    global _openai_client
    
    if not cls.API_KEY:
        logger.warning("LLM_API_KEY not configured - LLM features disabled")
        return False
    
    # Test connection with new OpenAI client
    try:
        if cls.PROVIDER == "openai":
            _openai_client = OpenAI(api_key=cls.API_KEY)
            # Test the connection by making a simple list models request
            _openai_client.models.list()  # ✅ NEW API
    except (APIConnectionError, APIStatusError, APITimeoutError) as e:
        logger.error(f"LLM configuration invalid: {e}")
        return False
    except Exception as e:
        logger.error(f"LLM configuration error: {e}")
        return False
    
    logger.info(f"LLM configured: {cls.PROVIDER} / {cls.MODEL}")
    return True
```

**Changes:**
- Created global `_openai_client` instead of using module-level `openai.api_key`
- Changed `openai.Model.list()` to `_openai_client.models.list()`
- Added specific exception handling for OpenAI errors
- Better error messages

---

#### Fix 1.4: stream_response() Method - Chat Completion Call (Lines 368-381)

**Before:**
```python
if LLMConfig.PROVIDER == "openai":
    response_stream = openai.ChatCompletion.create(
        api_key=LLMConfig.API_KEY,
        model=LLMConfig.MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=LLMConfig.TEMPERATURE,
        max_tokens=LLMConfig.MAX_TOKENS,
        timeout=LLMConfig.TIMEOUT,
        stream=True,
    )
else:
    raise ValueError(f"Unsupported LLM provider: {LLMConfig.PROVIDER}")
```

**After:**
```python
if LLMConfig.PROVIDER == "openai":
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=LLMConfig.API_KEY)
    
    response_stream = _openai_client.chat.completions.create(
        model=LLMConfig.MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=LLMConfig.TEMPERATURE,
        max_tokens=LLMConfig.MAX_TOKENS,
        timeout=LLMConfig.TIMEOUT,
        stream=True,
    )
else:
    raise ValueError(f"Unsupported LLM provider: {LLMConfig.PROVIDER}")
```

**Changes:**
- Use `_openai_client.chat.completions.create()` instead of `openai.ChatCompletion.create()`
- Remove `api_key` parameter (already set in client initialization)
- Ensure client is initialized if needed
- API key is no longer passed to each call - it's part of the client

---

#### Fix 1.5: stream_response() Method - Response Processing (Lines 389-451)

**Before:**
```python
for chunk in response_stream:
    choices = chunk.get("choices", [])  # ❌ Dict access
    if not choices:
        continue
    
    delta = choices[0].get("delta", {})  # ❌ Dict access
    
    # Handle text content
    if "content" in delta and delta["content"]:  # ❌ Dict key check
        content = delta["content"]
        accumulated_content += content
        
        yield json.dumps({...}) + "\n"
    
    # Handle tool calls
    if "tool_calls" in delta:  # ❌ Dict key check
        for tool_call in delta["tool_calls"]:
            accumulated_tool_call += json.dumps(tool_call)
            ...
```

**After:**
```python
for chunk in response_stream:
    choices = chunk.choices  # ✅ Object attribute
    if not choices:
        continue
    
    delta = choices[0].delta  # ✅ Object attribute
    
    # Handle text content
    if delta.content:  # ✅ Attribute check
        content = delta.content
        accumulated_content += content
        
        yield json.dumps({...}) + "\n"
    
    # Handle tool calls
    if delta.tool_calls:  # ✅ Attribute check
        for tool_call in delta.tool_calls:
            # Convert tool_call object to dict for JSON serialization
            tool_call_dict = {
                "id": tool_call.id,
                "type": "function",
                "function": {
                    "name": tool_call.function.name if tool_call.function else "",
                    "arguments": tool_call.function.arguments if tool_call.function else ""
                }
            }
            accumulated_tool_call = json.dumps(tool_call_dict)
            ...
```

**Changes:**
- Changed from dict-style `.get()` access to object attribute access
- New API returns objects, not dicts - cleaner syntax
- Tool calls need to be converted from objects to dicts for JSON serialization
- Safer null checking with object attributes

---

## File 2: `frontend/templates/dashboard.html`

### Issue: JWT Token Not Sent with API Requests

Chat API endpoints require JWT authentication, but fetch calls were only sending CSRF tokens.

### Fixes Applied

#### Fix 2.1: Add JWT Helper Function

**Added at the start of `<script>` section:**
```javascript
// Build fetch headers with JWT authentication
function getHeaders(includeContentType = true) {
  const headers = {
    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
  };
  if (includeContentType) {
    headers['Content-Type'] = 'application/json';
  }
  
  // Add Authorization header with JWT token
  const token = localStorage.getItem('jwt_token');
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  } else {
    console.warn('⚠️ No JWT token found. Did token minting fail?');
  }
  return headers;
}
```

**Purpose:** Centralized function to build fetch headers with CSRF + JWT tokens.

---

#### Fix 2.2: Add Token Minting on Page Load

**Added:**
```javascript
// Mint token on page load
window.addEventListener('load', function() {
  // Call mint-token endpoint to create JWT
  fetch('/mint-token/', { method: 'GET' })
    .then(r => {
      if (!r.ok) throw new Error(`Failed to mint token: HTTP ${r.status}`);
      return r.json();
    })
    .then(data => {
      if (data.token) {
        // Store JWT token in localStorage for all future requests
        localStorage.setItem('jwt_token', data.token);
        console.log(`✅ Token minted for ${data.username} (role: ${data.user_role})`);
      }
      // Load sessions after token is ready
      loadSessions();
    })
    .catch(err => {
      console.error('❌ Token minting failed:', err);
      alert('Failed to authenticate. Please refresh the page and try again.');
    });
});
```

**Purpose:** 
- Automatically mint JWT token when page loads
- Store in localStorage for later use
- Only load sessions after token is ready

---

#### Fix 2.3: Update API Fetch Calls

**Before:**
```javascript
fetch('/api/chat/session/', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content,
  },
  body: JSON.stringify({ title, context: {} })
})
```

**After:**
```javascript
fetch('/api/chat/session/', {
  method: 'POST',
  headers: getHeaders(true),  // ✅ Now includes JWT
  body: JSON.stringify({ title, context: {} })
})
```

**Applied to:**
- `fetch('/api/chat/session/', ...)` - Create chat
- `fetch('/api/chat/sessions/?limit=10', ...)` - List sessions
- `fetch('/api/chat/history/?session_id=...', ...)` - Load history
- `fetch('/api/chat/message/', ...)` - Send message

---

## File 3: `frontend/views.py`

### Issue: mint_token() Endpoint Not Returning Token

The endpoint creates a JWT but doesn't return it to the frontend, so JavaScript can't store it.

### Fixes Applied

#### Fix 3.1: Enhanced mint_token() Function (Lines 47-76)

**Before:**
```python
@login_required
def mint_token(request):
    # You can keep this endpoint for explicit "refresh token" if needed
    token = AccessToken.for_user(request.user)
    request.session["access_jwt"] = str(token)
    return JsonResponse({"ok": True})
```

**After:**
```python
@login_required
def mint_token(request):
    """
    Mint a new JWT token for the authenticated user.
    
    Returns:
        - token (str): JWT token to use in Authorization header for API calls
        - user_id (str): The authenticated user's ID
        - username (str): The authenticated user's username
        - user_role (str): The user's primary role (from user profile or 'user' default)
    
    Usage:
        Fetch /mint-token/ to get a fresh JWT token
        Use the token in: Authorization: Bearer <token>
    """
    token = AccessToken.for_user(request.user)
    token_str = str(token)
    request.session["access_jwt"] = token_str
    
    # Get user role if available (from user profile or default to 'user')
    user_role = getattr(request.user, 'user_role', 'user')
    if hasattr(request.user, 'profile') and hasattr(request.user.profile, 'role'):
        user_role = request.user.profile.role
    
    return JsonResponse({
        "ok": True,
        "token": token_str,           # ✅ NEW: Return token
        "user_id": str(request.user.id),
        "username": request.user.username,
        "user_role": user_role
    })
```

**Changes:**
- Return the actual JWT token string in response
- Include user metadata (id, username, role)
- Add docstring explaining the endpoint
- Frontend can now store and use the token

---

## How the Fixes Work Together

### Before (Broken)
```
1. Frontend loads
2. mint_token() called → Creates JWT but doesn't return it
3. API calls made without Authorization header
4. Django rejects with 401 Unauthorized ❌
```

### After (Fixed)
```
1. Frontend loads
2. mint_token() called → Creates JWT and returns it
3. Frontend stores JWT in localStorage
4. API calls include: Authorization: Bearer <jwt> ✅
5. Django accepts request and processes normally ✅
6. LLM responds (if OpenAI API is up to date) ✅
```

---

## Installation Steps

1. **Update OpenAI package:**
   ```bash
   pip install --upgrade openai
   ```

2. **Restart Django:**
   ```bash
   python manage.py runserver
   ```

3. **Test:**
   - Open http://localhost:8000
   - Check browser console for: `✅ Token minted for [username]`
   - Click "+ New Chat"
   - Send a message
   - See LLM response

---

## Verification Checklist

- [ ] OpenAI package updated: `pip list | grep openai`
- [ ] Django restarted after code changes
- [ ] No 401 errors on chat endpoints
- [ ] No 500 errors on chat/message endpoint
- [ ] Browser console shows successful token minting
- [ ] Can create new chat sessions
- [ ] Can send messages
- [ ] LLM responds to queries

---

**Status:** All fixes applied and ready for testing ✅
