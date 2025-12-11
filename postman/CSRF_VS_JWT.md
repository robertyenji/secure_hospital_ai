# CSRF vs JWT: What You Need to Know

## Side-by-Side Comparison

### How They Work

#### CSRF (Cross-Site Request Forgery Protection)
```
1. User loads form page
   ↓
2. Django generates CSRF token
   ↓
3. Token stored in cookie AND in hidden form field
   ↓
4. User submits form
   ↓
5. Django verifies:
   - Cookie token == Form field token?
   - If yes → Accept request
   - If no → 403 Forbidden
```

**Use case:** Traditional HTML forms

#### JWT (JSON Web Token)
```
1. User submits credentials to /api/token/
   ↓
2. Django verifies username/password
   ↓
3. Creates signed JWT token
   ↓
4. Client stores token in memory/localStorage
   ↓
5. For each API request, client sends:
   Authorization: Bearer <token>
   ↓
6. Django verifies:
   - Token signature valid?
   - Token not expired?
   - If yes → Accept request
   - If no → 401 Unauthorized
```

**Use case:** REST APIs, SPAs, Mobile apps

---

## Your Specific Situation

### Current Request (Broken ❌)
```
POST /mcp-proxy/?username=yenji100&password=kingjulien100

Headers: (nothing relevant)
Body: (empty or raw JSON)

Processing:
1. Django sees POST request
2. CSRF middleware checks for CSRF token
3. ❌ No token found in request
4. ❌ No token in POST data
5. ❌ No token in headers
6. → 403 CSRF token missing
```

### Why It Fails
- **No CSRF token** in request
- **Credentials in URL** (very insecure!)
- **No Authorization header**
- **Middleware checks CSRF before view executes**

---

## Solution: Use JWT Instead

### Fixed Request (Working ✅)
```
Step 1: Get Token
POST /api/token/
Headers:
  Content-Type: application/json
Body:
  {"username":"yenji100","password":"kingjulien100"}

Response:
  {"access":"eyJ0eXAi...","refresh":"eyJ0eXAi..."}

Step 2: Use Token
POST /mcp-proxy/
Headers:
  Authorization: Bearer eyJ0eXAi...
  Content-Type: application/json
Body:
  {"jsonrpc":"2.0","id":1,...}

Processing:
1. DRF JWTAuthentication middleware checks Authorization header
2. ✅ Token signature verified
3. ✅ Token not expired
4. ✅ User authenticated
5. View executes and returns result
```

### Why It Works
- **Secure token** in Authorization header
- **No credentials in URL**
- **Credentials only sent once** to /api/token/
- **Stateless** (no session needed)
- **Works for mobile/SPA** clients

---

## Decision Matrix

Choose based on your use case:

```
┌─────────────────────────────────────────────────────┐
│ What are you building?                               │
├─────────────────────────────────────────────────────┤
│                                                      │
│ Traditional Django + HTML forms                     │
│ → Use CSRF (already enabled)                        │
│                                                      │
│ REST API (JSON endpoints)                           │
│ → Use JWT (your situation) ✓                        │
│                                                      │
│ Single Page App (React, Vue, Angular)               │
│ → Use JWT (best practice)                           │
│                                                      │
│ Mobile app                                          │
│ → Use JWT (only option)                             │
│                                                      │
│ Mix of forms + APIs                                 │
│ → Use both: CSRF for /forms/*, JWT for /api/*      │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## Feature Comparison Table

| Feature | CSRF | JWT |
|---------|------|-----|
| **Security Type** | Cross-site attack prevention | Authentication/Authorization |
| **Token Location** | Cookie + Form field | Authorization header |
| **Scope** | One website | Multiple servers possible |
| **Session Required** | Yes | No (stateless) |
| **Mobile Friendly** | No | Yes |
| **Cookies Required** | Yes | No |
| **CORS Issues** | Yes | No |
| **Scalability** | Limited | Excellent |
| **API Friendly** | Poor | Excellent |
| **Backend Load** | Session storage needed | No session storage |
| **Token Expiry** | Not applicable | Configurable (8hr, 7day) |
| **Refresh Mechanism** | N/A | refresh_token endpoint |
| **Setup Complexity** | Simple | Medium |
| **Code Complexity** | Medium | Low |

---

## Code Comparison

### Before (Broken - CSRF approach)
```python
@login_required
@require_POST
def mcp_proxy(request):
    # This expects:
    # 1. User to be logged in (Django session)
    # 2. CSRF token in POST data
    # 3. But you're not providing CSRF token → 403 error
    
    access_jwt = request.session.get("access_jwt")
    # ...rest of code...
```

**Issues:**
- Relies on Django sessions
- Requires CSRF token in POST data
- Credentials in URL params (insecure)
- Not suitable for APIs

### After (Fixed - JWT approach)
```python
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mcp_proxy(request):
    # This expects:
    # 1. JWT token in Authorization header
    # 2. Valid token signature
    # 3. Token not expired
    # Then request.user is automatically set
    
    user = request.user  # Automatically authenticated
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    access_jwt = auth_header.replace('Bearer ', '')
    # ...rest of code...
```

**Benefits:**
- Stateless (no session storage)
- Token in Authorization header (standard)
- Credentials only sent once (secure)
- Perfect for APIs
- No CSRF needed

---

## The HTTP Flow Comparison

### CSRF-Protected Form (traditional)
```
Browser                                Django
  │                                      │
  ├─ GET /form ─────────────────────────>
  │                                      │ Generate CSRF token
  |<─ HTML form with CSRF token ────────┤
  │                                      │
  ├─ POST /form (with CSRF token) ─────>
  │                                      │ Verify CSRF token
  │<─ 200 OK ──────────────────────────┤
  │                                      │
```

### JWT-Protected API (modern)
```
Client                                Django
  │                                      │
  ├─ POST /api/token ──────────────────>
  │   (username, password)              │ Verify credentials
  │<─ JWT token ────────────────────────┤
  │                                      │
  ├─ POST /api/endpoint ────────────────>
  │   (Authorization: Bearer <token>)   │ Verify JWT signature
  │<─ 200 OK ──────────────────────────┤
  │                                      │
  ├─ POST /api/endpoint ────────────────>
  │   (Authorization: Bearer <token>)   │ Verify JWT signature
  │<─ 200 OK ──────────────────────────┤
  │                                      │
  │ (Token expires after 8 hours)       │
  │                                      │
  ├─ POST /api/token/refresh ─────────>
  │   (refresh_token)                   │ Issue new access token
  │<─ New JWT token ───────────────────┤
  │                                      │
```

---

## Your Django Configuration Already Has JWT

### Evidence in your code

```python
# secure_hospital_ai/settings.py

# ✅ REST Framework JWT configured
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
}

# ✅ JWT tokens configured
SIMPLE_JWT = {
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get("AUTH_JWT_SECRET", ...),
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# ✅ JWT endpoints configured
urlpatterns = [
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
```

**You have JWT fully configured. You just need to use it!**

---

## Migration Guide: CSRF → JWT

### For Your `/mcp-proxy/` Endpoint

#### Current (Broken)
```python
@login_required
@require_POST
def mcp_proxy(request):
    # Expects CSRF token (doesn't have it) → 403 Error
```

#### Fixed (Works)
```python
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mcp_proxy(request):
    # Expects JWT in Authorization header → Works!
```

---

## Security Considerations

### CSRF Token
```
Pros:
  ✅ Prevents CSRF attacks on forms
  ✅ Built into Django
  ✅ Automatic for most cases
  
Cons:
  ❌ Complex for APIs
  ❌ CORS restrictions
  ❌ Not suitable for mobile
```

### JWT Token
```
Pros:
  ✅ Stateless and scalable
  ✅ Works across domains
  ✅ Perfect for APIs/mobile
  ✅ No server-side session storage
  
Cons:
  ❌ Token revocation is complex
  ❌ Can't revoke issued tokens (until expiry)
  ❌ Need to handle expired tokens
```

### Best Practice: Use Both
```
├─ HTML Forms → CSRF + Sessions
└─ REST APIs → JWT (no CSRF)
```

---

## FAQ

**Q: Why Django CSRF for forms if we have JWT?**
A: CSRF prevents attackers from forging form submissions. JWT is for API authentication.

**Q: Can JWT prevent CSRF?**
A: No. JWT authenticates requests, CSRF prevents forged requests. Different problems.

**Q: Should I remove CSRF middleware?**
A: No. Keep it for forms, just disable for API endpoints using `@api_view`.

**Q: How do I disable CSRF for one view?**
A: Use `@api_view` (DRF handles it) or `@csrf_exempt` (if not using DRF).

**Q: Can I use both CSRF and JWT on same endpoint?**
A: Yes, but redundant. Pick one based on your client type.

**Q: How long should JWT tokens live?**
A: 8 hours for access, 7 days for refresh (your settings are good).

**Q: What if JWT expires during API call?**
A: Frontend catches 401, calls /api/token/refresh/, retries request.

---

## Decision Made For You

### Your Endpoint (`/mcp-proxy/`)
- **Type:** REST API endpoint (JSON-RPC)
- **Client:** Frontend/SPA/Mobile
- **Best Auth:** JWT ✓
- **CSRF needed:** No (API endpoints don't need CSRF)
- **Implementation:** DRF with JWTAuthentication

### Your Form Endpoints (if any)
- **Type:** HTML form submission
- **Client:** Browser
- **Best Auth:** CSRF + Sessions ✓
- **JWT needed:** No (forms use CSRF)
- **Implementation:** Django default

---

## Your Action Plan

1. ✅ Understand JWT vs CSRF (read above)
2. ✅ Review fixed code (frontend/views_fixed.py)
3. ⬜ Implement fix (copy fixed code)
4. ⬜ Test JWT flow (use curl commands)
5. ⬜ Update frontend (to use JWT header)
6. ⬜ Verify all endpoints (test each one)

**That's it! The rest is just implementation details.**
