# Project Review: CSRF Token Missing Error

## Executive Summary

Your project has a **CSRF token missing (403 Forbidden)** error on the `/mcp-proxy/` endpoint because:

1. ❌ Django's CSRF middleware is enabled (good for security)
2. ❌ Your endpoint is not exempt from CSRF checks
3. ❌ Your requests don't include CSRF tokens
4. ❌ You're using insecure query parameter authentication

## Root Cause Analysis

### Current Architecture
```
Your Request
    ↓
Django CSRF Middleware checks for CSRF token
    ↓
❌ No token found → 403 Forbidden
    ↓
Request blocked before reaching your view
```

### Problem Areas

| File | Line | Issue | Severity |
|------|------|-------|----------|
| `frontend/views.py` | 36-37 | Missing `@csrf_exempt` or JWT auth | 🔴 Critical |
| Your request | N/A | Using query params for auth (`?username=...&password=...`) | 🔴 Critical |
| `secure_hospital_ai/settings.py` | 123 | CSRF middleware enabled but not configured for API | 🟡 Medium |

### Why This Happens

Django has two separate security mechanisms:

1. **CSRF Protection** (for traditional forms)
   - Prevents Cross-Site Request Forgery
   - Requires a token in POST requests
   - Suitable for HTML forms

2. **JWT Authentication** (for APIs)
   - Uses tokens in Authorization header
   - Stateless and scalable
   - Better for REST APIs

**Your situation:** You're mixing both approaches without properly configuring either one.

---

## Recommended Solution

### ✅ Use JWT Token-Based Authentication

**Why this is best:**
- Your project already has JWT configured
- Stateless (no session needed)
- Works for APIs, SPAs, and mobile clients
- No CSRF needed for API endpoints
- More secure than query parameters

### Implementation Summary

1. **Fix the view** - Use DRF decorators with JWT
2. **Update client** - Get token first, then use in Authorization header
3. **Test** - Verify with curl/Postman

---

## Quick Reference

### The Error
```
Forbidden (CSRF token missing.): /mcp-proxy/
POST /mcp-proxy/?username=yenji100&password=kingjulien100
```

### The Fix
```python
# Before (broken)
@login_required
@require_POST
def mcp_proxy(request):
    ...

# After (fixed)
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mcp_proxy(request):
    ...
```

### How to Test
```bash
# 1. Get JWT token
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"yenji100","password":"kingjulien100"}'

# 2. Use token with mcp-proxy
curl -X POST http://localhost:8000/mcp-proxy/ \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools.call",...}'
```

---

## Project Structure Review

### ✅ Good Practices Found
- JWT already configured in settings
- DRF installed and available
- Role-based access control (RBAC)
- Audit logging implemented
- Environment-based configuration
- UUID primary keys for security

### ⚠️ Areas Needing Attention

| Area | Current State | Recommendation |
|------|---------------|-----------------|
| CSRF | Enabled but misconfigured | Use JWT for APIs, keep CSRF for forms |
| Authentication | Mixed (sessions + JWT) | Standardize on JWT for /api/* routes |
| Query Parameters | Using for credentials | Move to POST body or Authorization header |
| Secrets | Using .env file | ✅ Good, ensure not committed to git |
| CORS | corsheaders installed | Configure properly if frontend is separate |
| HTTPS | Not visible in settings | ✅ Add in production |

---

## Documentation Created

For detailed information, see these files:

1. **CSRF_FIX_SUMMARY.md** ← Start here for quick fix
2. **CSRF_FIX_ANALYSIS.md** ← Detailed technical analysis
3. **AUTHENTICATION_FLOW.md** ← Visual diagrams and comparisons
4. **IMPLEMENTATION_GUIDE.md** ← Step-by-step implementation
5. **frontend/views_fixed.py** ← Corrected code with full documentation

---

## Action Items

### Immediate (Required)
- [ ] Review `CSRF_FIX_SUMMARY.md`
- [ ] Replace `frontend/views.py` with `frontend/views_fixed.py` content
- [ ] Test JWT token flow
- [ ] Update frontend/API client to use JWT

### Short-term (Important)
- [ ] Test all endpoints for CSRF/auth compliance
- [ ] Configure CORS if frontend is separate
- [ ] Add rate limiting to `/api/token/` endpoint
- [ ] Update documentation with new auth flow

### Medium-term (Nice to have)
- [ ] Implement JWT refresh token rotation
- [ ] Add API versioning
- [ ] Create API documentation (Swagger/OpenAPI)
- [ ] Add comprehensive test suite

---

## Architecture Recommendations

### Current State (Mixed)
```
Request → Session Auth OR JWT Auth → CSRF Check (middleware) → View
         (confusing, inconsistent)
```

### Recommended State
```
HTML Forms → Session Auth + CSRF Check → Template View
API Calls → JWT Auth (no CSRF needed) → DRF View
```

---

## Settings Already Configured

You already have everything needed:

```python
# secure_hospital_ai/settings.py

# ✅ JWT is configured
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
}

# ✅ SIMPLE_JWT is configured
SIMPLE_JWT = {
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get("AUTH_JWT_SECRET", "dev-override-change-me"),
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

# ✅ JWT endpoint exists
# GET /api/token/ for TokenObtainPairView
# GET /api/token/refresh/ for TokenRefreshView
```

**You just need to use these existing configurations correctly!**

---

## Summary Table

| Aspect | Current | Recommended | Status |
|--------|---------|-------------|--------|
| **Authentication** | Mixed (sessions + JWT) | JWT for APIs | 🟡 Needs fix |
| **Authorization** | CSRF + login_required | JWTAuth + permission_classes | 🟡 Needs fix |
| **CSRF Protection** | Enabled globally | Only for forms | 🟡 Needs config |
| **JWT Config** | Present | In use | ✅ Good |
| **Error Handling** | Basic | Consistent responses | 🟡 Could improve |
| **Audit Logging** | Implemented | In use | ✅ Good |
| **RBAC** | Implemented | Integrated | ✅ Good |

---

## Next Steps

1. **Read** `CSRF_FIX_SUMMARY.md` (5 min)
2. **Review** `frontend/views_fixed.py` (10 min)
3. **Implement** changes from `IMPLEMENTATION_GUIDE.md` (10 min)
4. **Test** with provided curl commands (5 min)
5. **Verify** all endpoints work correctly (10 min)

**Total time: ~40 minutes**

---

## Questions & Resources

### Common Questions

**Q: Why not just add `@csrf_exempt`?**
A: That removes all CSRF protection. JWT is better for APIs.

**Q: Will this break my frontend?**
A: Only if it depends on CSRF. Update it to use JWT tokens.

**Q: How do I securely store the JWT token?**
A: Browser SPA → localStorage/sessionStorage, Mobile → Keychain/Keystore, Backend → Session

**Q: How do I refresh expired tokens?**
A: Use the `/api/token/refresh/` endpoint (already configured)

### Resources
- Django REST Framework JWT: https://django-rest-framework-simplejwt.readthedocs.io/
- CSRF Protection: https://docs.djangoproject.com/en/5.2/topics/security/
- JWT Best Practices: https://tools.ietf.org/html/rfc8725

---

## Support

All analysis and fix recommendations are in the documents created. If you have questions:

1. Check the relevant document
2. Review the code examples
3. Test with the provided curl commands
4. Check Django/DRF documentation

You have all the tools and information needed to fix this!
