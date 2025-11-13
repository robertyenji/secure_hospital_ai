# Visual Summary - CSRF Error & JWT Solution

## The Error in One Picture

```
┌─────────────────────────────────────────────────────────┐
│                    YOUR REQUEST                         │
├─────────────────────────────────────────────────────────┤
│ POST /mcp-proxy/?username=yenji100&password=kingjulien  │
│                                                          │
│ Headers:                                                │
│   (No CSRF token)                                       │
│   (No Authorization header)                             │
│                                                          │
│ Body:                                                   │
│   (empty or raw data)                                  │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│              DJANGO MIDDLEWARE PROCESSING               │
├─────────────────────────────────────────────────────────┤
│ 1. Is this a POST request?  → YES                       │
│ 2. Does it need CSRF token? → YES                       │
│ 3. Has CSRF token?          → NO ❌                      │
│                                                          │
│ RESULT: BLOCK REQUEST                                   │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                    RESPONSE: 403                        │
├─────────────────────────────────────────────────────────┤
│ Status: 403 Forbidden                                   │
│ Message: CSRF token missing                            │
│ (View never runs, request blocked at middleware)       │
└─────────────────────────────────────────────────────────┘
```

## The Solution in One Picture

```
┌─────────────────────────────────────────────────────────┐
│                   STEP 1: GET TOKEN                     │
├─────────────────────────────────────────────────────────┤
│ POST /api/token/                                        │
│ {"username":"yenji100","password":"kingjulien100"}     │
│                                                          │
│ Django verifies credentials ✓                           │
│ Returns: {"access":"eyJ0eXAi...","refresh":"..."}      │
└─────────────────────────────────────────────────────────┘
                          ↓
                    [Store Token]
                          ↓
┌─────────────────────────────────────────────────────────┐
│                 STEP 2: USE JWT TOKEN                   │
├─────────────────────────────────────────────────────────┤
│ POST /mcp-proxy/                                        │
│                                                          │
│ Headers:                                                │
│   Authorization: Bearer eyJ0eXAi...  ✓                  │
│   Content-Type: application/json      ✓                 │
│                                                          │
│ Body:                                                   │
│   {"jsonrpc":"2.0","id":1,...}  ✓                       │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│            JWT AUTHENTICATION MIDDLEWARE                │
├─────────────────────────────────────────────────────────┤
│ 1. Authorization header present?    → YES ✓             │
│ 2. Has Bearer token?                → YES ✓             │
│ 3. Token signature valid?           → YES ✓             │
│ 4. Token not expired?               → YES ✓             │
│                                                          │
│ RESULT: ALLOW REQUEST & SET USER                        │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                   VIEW EXECUTES                         │
├─────────────────────────────────────────────────────────┤
│ @api_view(['POST'])                                     │
│ @authentication_classes([JWTAuthentication])            │
│ @permission_classes([IsAuthenticated])                  │
│ def mcp_proxy(request):                                 │
│     user = request.user  # ✓ Authenticated!             │
│     # ... process tool call ...                         │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│                    RESPONSE: 200                        │
├─────────────────────────────────────────────────────────┤
│ Status: 200 OK ✓                                        │
│ Body: {"jsonrpc":"2.0","id":1,"result":{...}}          │
│ (Your tool result!)                                     │
└─────────────────────────────────────────────────────────┘
```

## Decision Tree

```
                    [API Endpoint?]
                           |
                ┌──────────┴──────────┐
                |                     |
              YES                    NO
                |                     |
                ↓                     ↓
            [Use JWT]          [Use CSRF]
                |                     |
         ┌──────┴──────┐       ┌──────┴──────┐
         |             |       |              |
    Mobile?     Browser SPA?   Forms?  Django Template?
         |             |       |              |
         ✓             ✓       ✓              ✓
       JWT            JWT     CSRF           CSRF


YOUR CASE: JSON-RPC API (REST)
→ Type: API Endpoint
→ Client: JavaScript/Frontend
→ Choice: JWT ✓
```

## Architecture Evolution

### Current (Broken)
```
Client → POST /mcp-proxy/?user=...&pass=...
           ↓
         CSRF Check
           ↓
         ❌ NO TOKEN → 403

Problem: Wrong approach for API endpoint
```

### Fixed (Working)
```
Client → POST /api/token/
           ↓
         Verify credentials
           ↓
         Issue JWT ← (access token)
           ↓
Client (with token) → POST /mcp-proxy/
                        ↓
                    JWT Check
                        ↓
                    ✅ Token valid → 200
```

## The Three Key Points

```
┌──────────────────────────────────────────────────────────┐
│  POINT 1: Your endpoint is an API (JSON-RPC)            │
├──────────────────────────────────────────────────────────┤
│  NOT a traditional HTML form                            │
│  → Should use API authentication (JWT)                  │
│  → NOT form authentication (CSRF)                       │
└──────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────────────────┐
│  POINT 2: JWT is already configured in Django          │
├──────────────────────────────────────────────────────────┤
│  ✓ rest_framework_simplejwt installed                   │
│  ✓ SIMPLE_JWT configured in settings                   │
│  ✓ /api/token/ endpoint exists                          │
│  → You just need to use it                              │
└──────────────────────────────────────────────────────────┘
        ↓
┌──────────────────────────────────────────────────────────┐
│  POINT 3: Simple 3-step fix                            │
├──────────────────────────────────────────────────────────┤
│  1. Add JWT decorators to view                          │
│  2. Get token from /api/token/                          │
│  3. Use token in Authorization header                   │
│  → Takes 15 minutes total                               │
└──────────────────────────────────────────────────────────┘
```

## Before & After Comparison

```
╔════════════════════════════════════════════════════════════╗
║                     BEFORE (Broken)                        ║
╠════════════════════════════════════════════════════════════╣
║                                                             ║
║  curl -X POST http://localhost:8000/mcp-proxy/ \          ║
║    ?username=yenji100&password=kingjulien100             ║
║                                                             ║
║  Headers:  (nothing)                                       ║
║  Result:   403 CSRF token missing                         ║
║  Problem:  Using CSRF approach for API endpoint           ║
║                                                             ║
║  Security Issues:                                          ║
║    ❌ Credentials in URL (visible in logs, history)       ║
║    ❌ No proper API authentication                        ║
║    ❌ Mixing session + CSRF concepts                      ║
║                                                             ║
╚════════════════════════════════════════════════════════════╝

╔════════════════════════════════════════════════════════════╗
║                     AFTER (Fixed)                          ║
╠════════════════════════════════════════════════════════════╣
║                                                             ║
║  # Step 1: Get token                                       ║
║  curl -X POST http://localhost:8000/api/token/ \          ║
║    -d '{"username":"yenji100","password":"kingjulien100"}' ║
║  Response: {"access":"eyJ0eXAi..."}                       ║
║                                                             ║
║  # Step 2: Use token                                       ║
║  curl -X POST http://localhost:8000/mcp-proxy/ \          ║
║    -H "Authorization: Bearer eyJ0eXAi..."                  ║
║                                                             ║
║  Result:   200 OK                                          ║
║  Response: {"jsonrpc":"2.0","result":{...}}               ║
║                                                             ║
║  Security Improvements:                                    ║
║    ✅ Credentials not in URL                              ║
║    ✅ Proper JWT API authentication                       ║
║    ✅ Standard RESTful approach                           ║
║    ✅ Stateless & scalable                               ║
║    ✅ Works for mobile apps                               ║
║                                                             ║
╚════════════════════════════════════════════════════════════╝
```

## Timeline to Fix

```
RIGHT NOW              IN 5 MIN                IN 10 MIN
  ↓                      ↓                       ↓
Read this          Copy the fixed code     Restart Django
  ↓                      ↓                       ↓
(2 min)            to views.py             And test!
                      (1 min)                (2 min)
```

## The Mental Model

```
API Authentication = Proving who you are
CSRF Protection = Preventing forged requests

Both needed?
  HTML Forms: YES + YES (both CSRF and auth)
  API Calls:  NO + YES (just auth via JWT)

Your endpoint:
  Type: API (JSON-RPC)
  Need: Auth only → Use JWT ✓
```

## Your Superpower Now

```
┌─────────────────────────────────────────┐
│ Before: Confused by CSRF vs JWT        │
├─────────────────────────────────────────┤
│ After:  Understand both completely     │
│         Know which to use when         │
│         Can explain to others          │
│         Can review code confidently    │
└─────────────────────────────────────────┘
```

---

**Next: Copy frontend/views_fixed.py to frontend/views.py and restart Django!**
