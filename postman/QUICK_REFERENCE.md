# Quick Reference Card - CSRF 403 Fix

## The Problem (One Line)
```
Your POST request doesn't have a CSRF token → Django rejects it → 403 Forbidden
```

## The Solution (One Line)
```
Use JWT token in Authorization header instead of CSRF token
```

## The Code Change (One Block)
```python
# ❌ BEFORE (broken)
@login_required
@require_POST
def mcp_proxy(request):
    ...

# ✅ AFTER (fixed)
@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mcp_proxy(request):
    ...
```

## The Implementation (3 Steps)

### Step 1: Get JWT Token
```bash
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"yenji100","password":"kingjulien100"}'

# Copy the "access" value from response
```

### Step 2: Use JWT in Request
```bash
curl -X POST http://localhost:8000/mcp-proxy/ \
  -H "Authorization: Bearer <PASTE_TOKEN_HERE>" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,...}'
```

### Step 3: See Result
```
Status: 200 OK ✅ (not 403!)
```

## Files to Know

| File | Action |
|------|--------|
| `frontend/views_fixed.py` | **Read** - See correct code |
| `frontend/views.py` | **Replace** - Copy above to this |
| `secure_hospital_ai/settings.py` | **Check** - JWT already configured |
| `CSRF_FIX_SUMMARY.md` | **Read** - Quick overview |
| `IMPLEMENTATION_GUIDE.md` | **Follow** - Step-by-step instructions |

## Key Differences

| Feature | CSRF | JWT |
|---------|------|-----|
| **Use** | HTML forms | REST APIs |
| **Token in** | Cookie/Form | Authorization header |
| **Stateless** | No | Yes ✓ |
| **Mobile** | No | Yes ✓ |
| **Your endpoint** | ❌ No | ✓ Yes |

## Testing (Before & After)

### Before (403 Error)
```bash
$ curl -X POST http://localhost:8000/mcp-proxy/
403 Forbidden
Reason: CSRF token missing
```

### After (200 OK)
```bash
$ curl -X POST http://localhost:8000/mcp-proxy/ \
  -H "Authorization: Bearer eyJ0eXAi..."
200 OK
{"jsonrpc":"2.0","id":1,"result":{...}}
```

## JavaScript Code
```javascript
// Step 1: Get token
const res = await fetch('/api/token/', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({username:'user', password:'pass'})
});
const {access} = await res.json();

// Step 2: Use token
const result = await fetch('/mcp-proxy/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({jsonrpc:'2.0', ...})
});
```

## Python Code
```python
import requests

# Step 1: Get token
r = requests.post('http://localhost:8000/api/token/', json={
    'username': 'yenji100', 'password': 'kingjulien100'
})
token = r.json()['access']

# Step 2: Use token
result = requests.post('http://localhost:8000/mcp-proxy/', 
    headers={'Authorization': f'Bearer {token}'},
    json={'jsonrpc': '2.0', ...}
)
```

## Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| 403 CSRF | No CSRF token | ✅ Use JWT (you're here) |
| 401 Unauthorized | No JWT token | Get one from /api/token/ first |
| 401 Invalid token | Token expired/wrong | Get fresh token |
| 400 Bad Request | Invalid JSON | Check JSON syntax |
| 502 Bad Gateway | MCP unreachable | Start MCP server |

## Checklist
- [ ] Read CSRF_FIX_SUMMARY.md (2 min)
- [ ] Copy frontend/views_fixed.py to frontend/views.py (1 min)
- [ ] Restart Django (1 min)
- [ ] Test: Get token from /api/token/ (1 min)
- [ ] Test: Call /mcp-proxy/ with token (1 min)
- [ ] Update frontend (varies)
- [ ] Verify error is gone ✅

## Key Points
✅ JWT is already configured in your Django settings
✅ You have everything needed, just need to use it
✅ No need to remove CSRF (keep it for forms)
✅ This endpoint is an API, APIs use JWT
✅ The fix takes 5 minutes to implement

## Remember
```
CSRF = Form Protection
JWT  = API Authentication

Your endpoint = API
Your choice   = JWT ✓
```

## Still Confused?
Read: CSRF_FIX_SUMMARY.md (2 min) or CSRF_VS_JWT.md (15 min)

## Ready to Implement?
Follow: IMPLEMENTATION_GUIDE.md

---
**Status: Ready to fix!** Copy frontend/views_fixed.py → frontend/views.py and restart Django.
