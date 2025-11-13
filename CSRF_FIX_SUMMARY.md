# CSRF Error Summary & Quick Fix

## The Error You're Getting
```
Forbidden (CSRF token missing.): /mcp-proxy/
POST /mcp-proxy/?username=yenji100&password=kingjulien100 HTTP/1.1" 403 2491
```

## Why It's Happening

1. **Django CSRF middleware is enabled** in your `settings.py`
2. **Your `/mcp-proxy/` endpoint requires POST** and has `@login_required`
3. **Your request is missing a CSRF token** in the POST data
4. **You're using query parameters for authentication** (insecure)

## Root Causes Analysis

| Issue | Location | Details |
|-------|----------|---------|
| CSRF enabled | `settings.py` line 123 | `'django.middleware.csrf.CsrfViewMiddleware'` |
| No CSRF exempt | `frontend/views.py` line 36 | `@login_required` + `@require_POST` without `@csrf_exempt` |
| Missing token | Your request | POST request has no CSRF token |
| Insecure auth | Your request | Using query params for username/password |

## The Fix (2 Options)

### Option A: Quick Fix (Not Recommended)
Add this to the view:
```python
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
@login_required
@require_POST
def mcp_proxy(request):
    ...
```
**Problem:** Removes all CSRF protection

### Option B: Recommended Fix - Use JWT Instead
Replace your view with JWT-based authentication. See `frontend/views_fixed.py` for the complete corrected implementation.

Key changes:
```python
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mcp_proxy(request):
    """Uses JWT token from Authorization header instead of CSRF"""
    ...
```

## How to Test the Fix

### Before (fails with 403):
```bash
curl -X POST http://localhost:8000/mcp-proxy/?username=yenji100&password=kingjulien100
```

### After (works with JWT):
```bash
# 1. Get JWT token
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"yenji100","password":"kingjulien100"}'

# Response: {"access":"eyJ0eXAiOiJKV1QiLCJhbGc...","refresh":"..."}

# 2. Use token to call mcp-proxy
curl -X POST http://localhost:8000/mcp-proxy/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":1,
    "method":"tools.call",
    "params":{"name":"get_patient_overview","arguments":{"patient_id":"ABC123"}}
  }'
```

## Files to Review
- `CSRF_FIX_ANALYSIS.md` - Detailed technical analysis
- `frontend/views_fixed.py` - Corrected implementation with full documentation
- `secure_hospital_ai/settings.py` - CSRF/Auth configuration

## Next Steps
1. Review `CSRF_FIX_ANALYSIS.md` for complete details
2. Copy `frontend/views_fixed.py` to `frontend/views.py`
3. Test with JWT token (see "How to Test the Fix" above)
4. Update any frontend code to use JWT headers instead of query params
