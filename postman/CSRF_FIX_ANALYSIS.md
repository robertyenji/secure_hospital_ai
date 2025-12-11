# CSRF Token Missing Error - Complete Analysis

## Problem Statement
You're getting a **403 Forbidden** error with message "CSRF token missing" when POSTing to `/mcp-proxy/`:

```
Forbidden (CSRF token missing.): /mcp-proxy/
[10/Nov/2025 18:16:50] "POST /mcp-proxy/?username=yenji100&password=kingjulien100 HTTP/1.1" 403 2491
```

## Root Causes

### 1. **CSRF Protection is Enabled in Settings**
```python
# In secure_hospital_ai/settings.py (line 123)
'django.middleware.csrf.CsrfViewMiddleware',
```
Django's CSRF middleware is active and protecting all POST requests.

### 2. **The `mcp_proxy` View Requires CSRF Token**
```python
# In frontend/views.py (line 36-37)
@login_required
@require_POST
def mcp_proxy(request):
```

The view has:
- `@login_required` - requires authentication
- `@require_POST` - requires POST method
- **BUT NO** `@csrf_exempt` decorator
- **AND** expects a CSRF token in the POST data or headers

### 3. **POST Request is Missing CSRF Token**
Your request:
```
POST /mcp-proxy/?username=yenji100&password=kingjulien100 HTTP/1.1
```

This is missing:
- CSRF token in the request body (as form data)
- CSRF token in the `X-CSRFToken` header
- Proper authentication setup

## Why This Happens

### Django CSRF Protection Flow:
1. User loads a Django form page → Django sets a CSRF token in cookie
2. Form includes `{% csrf_token %}` template tag → Token hidden in form
3. On form submission, Django validates the token
4. Without token, POST is rejected with 403

### Your Situation:
You're making a direct POST request without:
1. First fetching the CSRF token
2. Including it in your request

## Solutions

### **Solution 1: Disable CSRF for API Endpoint (Not Recommended for Production)**
```python
# frontend/views.py
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt  # ⚠️ Only for API endpoints, NOT for regular forms
@login_required
@require_POST
def mcp_proxy(request):
    # ... rest of code
```

**Pros:** Quick fix, works immediately
**Cons:** Removes CSRF protection, security risk

### **Solution 2: Use JWT Token-Based Authentication (Recommended)**
Since you're already using JWT tokens in your code, use JWT instead of Django sessions:

```python
# frontend/views.py
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mcp_proxy(request):
    """JWT-authenticated endpoint (no CSRF needed)"""
    # Remove session-based auth, use JWT token from header
    access_jwt = request.auth  # JWT token from Authorization header
    
    if not access_jwt:
        return Response(
            {"error": "No JWT token provided"},
            status=401
        )
    
    # ... rest of implementation
```

**Pros:** 
- No CSRF needed for API endpoints
- JWT is stateless and scalable
- Works for mobile/SPA clients

**Cons:** 
- Requires JWT in Authorization header

### **Solution 3: Include CSRF Token in Your Request**
If you want to use the current setup:

```bash
# 1. Get CSRF token first
curl -b cookies.txt http://localhost:8000/mcp-proxy/ > /dev/null

# 2. Extract token from response and include in POST
curl -b cookies.txt \
  -H "X-CSRFToken: <token-from-cookie>" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"tool":"get_patient_overview","patient_id":"ABC123"}' \
  http://localhost:8000/mcp-proxy/?username=yenji100&password=kingjulien100
```

**Pros:** Maintains current security
**Cons:** Extra complexity, less suitable for API clients

## Implementation Recommendation

### **Best Fix: Use Rest Framework with JWT**

Replace the current view:

```python
# frontend/views.py
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status as http_status

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mcp_proxy(request):
    """
    Accept JSON-RPC POST from the frontend (HTMX).
    Uses JWT authentication instead of CSRF.
    
    Expected header:
        Authorization: Bearer <jwt_token>
    
    Expected body:
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools.call",
            "params": {
                "name": "tool_name",
                "arguments": {
                    "patient_id": "..."
                }
            }
        }
    """
    # JWT is already validated by JWTAuthentication
    user = request.user
    
    # 1) Get JWT from Authorization header (DRF does this automatically)
    # 2) You can use request.user for authorization checks
    
    ctype = request.headers.get("Content-Type", "")
    payload = None

    if "application/json" in ctype:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return Response(
                {"error": "Invalid JSON"},
                status=http_status.HTTP_400_BAD_REQUEST
            )
    else:
        return Response(
            {"error": "Content-Type must be application/json"},
            status=http_status.HTTP_400_BAD_REQUEST
        )

    # Forward to MCP
    try:
        # Get the JWT token from the request
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        token = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''
        
        resp = requests.post(
            MCP_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-User-Id": str(user.pk),
                "X-User-Role": getattr(user, "role", ""),
            },
            json=payload,
            timeout=20,
        )
    except requests.RequestException as e:
        return Response(
            {"error": f"MCP unreachable: {e}"},
            status=http_status.HTTP_502_BAD_GATEWAY
        )

    # Return response
    try:
        data = resp.json()
    except ValueError:
        return Response(
            {"error": resp.text},
            status=resp.status_code
        )
    
    return Response(data, status=resp.status_code)
```

## How to Test the Fix

### Before change (will fail):
```bash
curl -X POST http://localhost:8000/mcp-proxy/?username=yenji100&password=kingjulien100
# Returns: 403 CSRF token missing
```

### After change (with JWT):
```bash
# 1. Get a token first
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "yenji100",
    "password": "kingjulien100"
  }'

# Returns:
# {
#   "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
#   "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
# }

# 2. Use the token in your POST
curl -X POST http://localhost:8000/mcp-proxy/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools.call",
    "params": {
      "name": "get_patient_overview",
      "arguments": {"patient_id": "ABC123"}
    }
  }'

# Returns: 200 OK with tool result
```

## Security Considerations

1. **Never use `@csrf_exempt` on API endpoints** - This removes CSRF protection entirely
2. **JWT tokens should be sent in Authorization header** - Not in query params (you're using query params which is insecure)
3. **HTTPS in production** - Tokens should only be transmitted over HTTPS
4. **Token expiration** - Your JWT is set to 8 hours, which is reasonable
5. **Secrets in environment variables** - Good practice, ensure JWT_SECRET is protected

## Additional Improvements Needed

1. **Move username/password from query params to POST body**
   ```python
   # Bad (current):
   POST /mcp-proxy/?username=yenji100&password=kingjulien100
   
   # Good (future):
   POST /api/token/
   {
     "username": "yenji100",
     "password": "kingjulien100"
   }
   ```

2. **Configure CORS properly** if frontend is separate
   ```python
   # In settings.py
   CORS_ALLOWED_ORIGINS = [
       "http://localhost:3000",  # React dev server
       "https://yourdomain.com",
   ]
   ```

3. **Add rate limiting** to prevent brute force
   ```python
   from rest_framework.throttling import UserRateThrottle
   
   @api_view(['POST'])
   @throttle_classes([UserRateThrottle])
   def mcp_proxy(request):
       ...
   ```

## Summary

| Issue | Cause | Fix |
|-------|-------|-----|
| 403 CSRF Missing | CSRF middleware enabled | Use JWT auth instead |
| POST required login | `@login_required` decorator | Works with JWT auth |
| Query param auth | Insecure practice | Use Authorization header |
| No token validation | Session-based auth | Use `JWTAuthentication` |

**Recommended action: Implement Solution 2 (JWT-based authentication)**
