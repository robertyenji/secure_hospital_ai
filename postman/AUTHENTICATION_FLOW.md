# CSRF vs JWT Authentication Flow

## Current Flow (BROKEN - Returns 403)

```
┌─────────────────────────────────────────────────────────┐
│ Your Request (MISSING CSRF Token)                       │
├─────────────────────────────────────────────────────────┤
│ POST /mcp-proxy/?username=yenji100&password=kingjulien100
│                                                          │
│ Headers:                                                │
│   (no CSRF token)                                       │
│   (no Authorization header)                             │
│                                                          │
│ Body:                                                   │
│   (empty or raw JSON)                                  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Django Middleware Processing                            │
├─────────────────────────────────────────────────────────┤
│ 1. AuthenticationMiddleware: No session/user info       │
│ 2. CsrfViewMiddleware: Checks for CSRF token            │
│    ❌ NO TOKEN FOUND IN REQUEST                         │
│    ❌ NO TOKEN IN POST DATA                             │
│    ❌ NO TOKEN IN HEADERS                               │
│                                                          │
│ Result: CSRF validation FAILS                           │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Response: 403 Forbidden                                 │
├─────────────────────────────────────────────────────────┤
│ Status: 403 CSRF token missing                          │
│ Message: Forbidden (CSRF token missing.): /mcp-proxy/   │
└─────────────────────────────────────────────────────────┘
```

## Fixed Flow (RECOMMENDED - Uses JWT)

```
┌─────────────────────────────────────────────────────────┐
│ Step 1: Get JWT Token                                   │
├─────────────────────────────────────────────────────────┤
│ POST /api/token/                                        │
│ Content-Type: application/json                          │
│                                                          │
│ {                                                       │
│   "username": "yenji100",                               │
│   "password": "kingjulien100"                           │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Django JWT Authentication                               │
├─────────────────────────────────────────────────────────┤
│ 1. Verify username/password                             │
│ 2. Create JWT token (if valid)                          │
│ 3. Return access token to client                        │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Response: 200 OK                                        │
├─────────────────────────────────────────────────────────┤
│ {                                                       │
│   "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",             │
│   "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."             │
│ }                                                       │
│                                                          │
│ ✅ Token extracted by client and stored                │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Step 2: Call MCP Proxy with JWT                         │
├─────────────────────────────────────────────────────────┤
│ POST /mcp-proxy/                                        │
│                                                          │
│ Headers:                                                │
│   Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...      │
│   Content-Type: application/json                        │
│   X-User-Id: 550e8400-e29b-41d4-a716-446655440000     │
│   X-User-Role: Doctor                                  │
│                                                          │
│ Body:                                                   │
│ {                                                       │
│   "jsonrpc": "2.0",                                     │
│   "id": 1,                                              │
│   "method": "tools.call",                               │
│   "params": {                                           │
│     "name": "get_patient_overview",                     │
│     "arguments": {"patient_id": "ABC123"}              │
│   }                                                     │
│ }                                                       │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ DRF JWT Authentication (@JWTAuthentication)             │
├─────────────────────────────────────────────────────────┤
│ 1. Extract token from "Authorization: Bearer ..." header│
│ 2. Decode JWT using JWT_SECRET                         │
│ 3. Validate signature and expiration                    │
│ 4. Set request.user to authenticated user              │
│ 5. Skip CSRF check (API endpoints don't need CSRF)      │
│                                                          │
│ ✅ AUTHENTICATION SUCCESSFUL                           │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ mcp_proxy View Execution                                │
├─────────────────────────────────────────────────────────┤
│ 1. Parse JSON-RPC payload from request body             │
│ 2. Forward to MCP server with JWT token                 │
│ 3. Relay MCP response back to client                    │
│                                                          │
│ ✅ VIEW PROCESSES REQUEST SUCCESSFULLY                 │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Response: 200 OK (with tool result)                     │
├─────────────────────────────────────────────────────────┤
│ {                                                       │
│   "jsonrpc": "2.0",                                     │
│   "id": 1,                                              │
│   "result": {                                           │
│     "patient_id": "ABC123",                             │
│     "name": "John Doe",                                 │
│     ...                                                 │
│   }                                                     │
│ }                                                       │
│                                                          │
│ ✅ SUCCESS                                              │
└─────────────────────────────────────────────────────────┘
```

## Why JWT is Better Than CSRF for APIs

| Aspect | CSRF | JWT |
|--------|------|-----|
| **How it works** | Hidden form token | Explicit Bearer token |
| **Best for** | Traditional forms | REST APIs, SPAs, Mobile |
| **Token location** | Form data, cookie | Authorization header |
| **Stateless** | No (requires session) | Yes |
| **Scalable** | No (relies on cookies) | Yes |
| **Mobile-friendly** | No (cookies complex) | Yes |
| **CORS-friendly** | No (CSRF restrictions) | Yes |

## Settings That Affect This

### CSRF Enabled (Causes Error)
```python
# secure_hospital_ai/settings.py
MIDDLEWARE = [
    ...
    'django.middleware.csrf.CsrfViewMiddleware',  # ← This is the problem
    ...
]
```

### JWT Configuration
```python
# secure_hospital_ai/settings.py
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",  # ← This is the solution
        "rest_framework.authentication.SessionAuthentication",
    ),
}

SIMPLE_JWT = {
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get("AUTH_JWT_SECRET", "dev-override-change-me"),
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}
```

## Security Best Practices

### ✅ DO THIS (Secure)
```bash
# Use Bearer token in Authorization header
curl -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
     http://localhost:8000/api/endpoint/
```

### ❌ DON'T DO THIS (Insecure)
```bash
# Don't put credentials in URL query params
curl http://localhost:8000/api/endpoint/?username=user&password=pass

# Don't put tokens in URL query params
curl http://localhost:8000/api/endpoint/?token=eyJ0eXAiOiJKV1QiLCJhbGc...
```

### ⚠️ DEVELOPMENT ONLY
```bash
# Don't use @csrf_exempt on real endpoints
@csrf_exempt
def my_view(request):
    ...
```
