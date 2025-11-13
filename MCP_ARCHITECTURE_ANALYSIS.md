# MCP Architecture Analysis - CSRF Fix (Revised)

## Your Real Architecture

```
┌─────────────────────┐
│  Frontend (Browser) │
│  or Mobile Client   │
└──────────┬──────────┘
           │ 
           │ POST /mcp-proxy/
           │ with JWT token
           │
           ↓
┌──────────────────────────────────┐
│   Django Proxy Server            │  ← YOU ARE HERE (403 error)
│   (secure_hospital_ai)           │
│   - Receives JWT token           │
│   - Should forward to MCP        │
│   - CSRF middleware blocking it  │
└──────────┬───────────────────────┘
           │
           │ Forward JWT token to MCP
           │ Authorization: Bearer <token>
           │
           ↓
┌──────────────────────────────────┐
│   FastAPI MCP Server             │  ← Port 9000
│   (mcp_server/main.py)           │
│   - Validates JWT                │
│   - Enforces RBAC                │
│   - Redacts PHI                  │
│   - Returns results              │
└──────────────────────────────────┘
```

## The Problem (Corrected Understanding)

### What's Happening
```
Client → POST /mcp-proxy/
         (with Authorization: Bearer <JWT>)
            ↓
         Django CSRF middleware
            ↓
         ❌ CSRF token check fails
         (before view even runs)
            ↓
         403 CSRF token missing
         (MCP server never gets called)
```

### Why It Matters
The CSRF check is **blocking at Django middleware level**, preventing your proxy view from ever executing. So even though you have proper JWT infrastructure downstream, Django is rejecting the request before it can reach your `/mcp-proxy/` view.

## The Solution (Corrected)

### For API Endpoints (Your Case)
```python
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mcp_proxy(request):
    """
    API endpoint - doesn't need CSRF, uses JWT instead
    
    - Receives JWT in Authorization header
    - Validates JWT (DRF handles this)
    - Extracts user_id and role from JWT claims
    - Forwards JWT token to MCP server
    - Relays MCP response back
    """
    user = request.user  # Authenticated via JWT
    
    # Get JWT from Authorization header
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    token = auth_header.replace('Bearer ', '')
    
    # Forward to MCP with JWT token
    resp = requests.post(
        'http://127.0.0.1:9000/mcp/',
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'X-User-Id': str(user.pk),
            'X-User-Role': getattr(user, 'role', ''),
        },
        json=request.body,
        timeout=20,
    )
    
    return Response(resp.json(), status=resp.status_code)
```

### Key Points
1. **`@api_view(['POST'])`** - DRF decorator, handles CSRF exception automatically
2. **`@authentication_classes([JWTAuthentication])`** - Use JWT, not sessions
3. **`@permission_classes([IsAuthenticated])`** - Require valid authentication
4. **JWT passed through** - MCP server gets the same token to validate

## JWT Secret Synchronization

Your `.env` has:
```
JWT_SECRET=a205f6e168cc0e41a353c77fa5d90cd7d530fa3f1d2bf443b6fa50cba705157c
JWT_ALG=HS256
```

### Django Settings
```python
SIMPLE_JWT = {
    "SIGNING_KEY": os.environ.get("JWT_SECRET"),  # ← Should use your .env JWT_SECRET
    "ALGORITHM": "HS256",
}
```

### MCP Server
```python
JWT_SECRET = os.getenv("JWT_SECRET")  # ← Also uses same .env JWT_SECRET
JWT_ALG = os.getenv("JWT_ALG", "HS256")
```

✅ **Good news:** Both are reading from the same `JWT_SECRET` in `.env`, so tokens will be compatible!

## The Flow (Step-by-Step)

### Step 1: Client Gets Token
```bash
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"yenji100","password":"kingjulien100"}'

# Django validates credentials
# Creates JWT with user_id and role claims
# Signs it with JWT_SECRET from .env
# Returns: {"access":"eyJ0eXAi...", "refresh":"..."}
```

### Step 2: Client Calls Django Proxy
```bash
curl -X POST http://localhost:8000/mcp-proxy/ \
  -H "Authorization: Bearer eyJ0eXAi..." \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,
    "method":"tools.call",
    "params":{"name":"get_patient_overview","arguments":{"patient_id":"P001"}}
  }'
```

### Step 3: Django Proxy Processing
```
Request arrives
    ↓
DRF checks Authorization header (JWTAuthentication)
    ↓
✅ Token signature valid (signed with same JWT_SECRET)
✅ Token not expired
    ↓
request.user is set to authenticated user
    ↓
View executes:
    - Extracts JWT from header
    - Forwards request to MCP server with JWT
    ↓
MCP server receives request
```

### Step 4: MCP Server Processing
```python
auth = request.headers.get("Authorization", "")
token = auth.split(" ", 1)[1]  # "eyJ0eXAi..."

# MCP decodes JWT using SAME JWT_SECRET from .env
claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])

user_id = claims.get("sub")  # or "user_id"
role = claims.get("role")    # or get from user lookup

# Validate RBAC
if not is_allowed(model, action, role, user_id, row_context):
    # Return 403 from MCP
else:
    # Execute tool
    # Redact PHI if necessary
    # Return result
```

### Step 5: Response Back
```
MCP server returns result
    ↓
Django proxy relays it
    ↓
Client receives JSON-RPC response
```

## Key Insight

Your system is actually **correctly designed**:

1. ✅ Django handles authentication (`/api/token/`)
2. ✅ Django creates JWT tokens with user claims
3. ✅ Django proxy forwards requests to MCP
4. ✅ MCP validates the same JWT tokens
5. ✅ MCP enforces RBAC based on JWT claims
6. ✅ All using same JWT_SECRET from `.env`

**The only issue:** Django's CSRF middleware is blocking the request before your proxy view can do its job.

## The Fix (Simple)

### Option A: DRF Decorators (Recommended)
```python
# Use Django REST Framework decorators
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mcp_proxy(request):
    # Now CSRF is handled automatically
    # JWT is validated automatically
    # You just forward to MCP
```

### Option B: CSRF Exempt (Not Recommended)
```python
# Only if you must use non-DRF approach
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@require_POST
def mcp_proxy(request):
    # CSRF is disabled (less secure)
    # But at least request gets through
```

**Use Option A** - it's the proper way for REST APIs.

## What You Already Have

Looking at your code:

```python
# secure_hospital_ai/settings.py
✅ rest_framework installed
✅ rest_framework_simplejwt installed
✅ REST_FRAMEWORK configured
✅ SIMPLE_JWT configured
✅ /api/token/ endpoint exists
✅ /api/token/refresh/ endpoint exists

# .env
✅ JWT_SECRET defined
✅ JWT_ALG defined

# mcp_server/main.py
✅ Expects JWT tokens
✅ Validates JWT with same secret
✅ Enforces RBAC
✅ Redacts PHI
✅ Logs audit events
```

## What Needs Changing

Only one thing:
- Update `/mcp-proxy/` view to use DRF decorators for JWT auth

Everything else is already correct!

## Test After Fix

```bash
# 1. Get JWT token
TOKEN=$(curl -s -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"yenji100","password":"kingjulien100"}' | jq -r .access)

# 2. Call mcp-proxy
curl -X POST http://localhost:8000/mcp-proxy/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0","id":1,"method":"tools.call",
    "params":{"name":"get_patient_overview","arguments":{"patient_id":"P001"}}
  }'

# 3. If you see MCP's response (not 403), it worked!
```

## Summary

Your CSRF 403 error is a **gateway problem**, not an architectural problem:

- ✅ Frontend → Django: needs JWT (which you have)
- ✅ Django → MCP: needs JWT (which you forward)
- ✅ MCP → Database: needs RBAC & Redaction (which you have)

**The fix:** Let requests through Django's CSRF middleware for API endpoints (use DRF + JWT).

Then the entire MCP architecture can work as designed:
1. Authenticate clients with JWT
2. Validate JWT at Django
3. Forward JWT to MCP
4. MCP validates and enforces security
5. Results flow back

This is a proper, layered security model!
