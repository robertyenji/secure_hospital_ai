# Implementation Guide: Fix CSRF Error

## Quick Overview
Your CSRF error happens because:
1. Django's CSRF middleware is enabled
2. Your `/mcp-proxy/` endpoint is a POST that requires authentication
3. You're not providing a CSRF token in your requests
4. You're using insecure query parameter authentication

**Solution:** Use JWT token-based authentication instead (already configured in your Django project)

---

## Step-by-Step Implementation

### Step 1: Backup Your Current Files
```bash
cd c:\Users\rober\Desktop\dev\secure_hospital_ai
cp frontend/views.py frontend/views.py.backup
```

### Step 2: Replace Your Views File
Option A - Automatic (recommended):
```bash
cp frontend/views_fixed.py frontend/views.py
```

Option B - Manual:
Copy the content from `frontend/views_fixed.py` and replace `frontend/views.py` entirely.

### Step 3: Update Your URL Configuration
Verify that your `frontend/urls.py` includes:
```python
path("mcp-proxy/", views.mcp_proxy, name="mcp_proxy"),  # Should already exist
```

### Step 4: Verify Settings
Check that `secure_hospital_ai/settings.py` has JWT configured:
```python
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
}
```

### Step 5: Restart Django
```bash
# Kill existing process
Ctrl+C

# Restart
python manage.py runserver
```

---

## Testing the Fix

### Prerequisites
You need:
- Running Django dev server on `http://localhost:8000`
- Valid credentials (username: `yenji100`, password: `kingjulien100`)
- A tool to make HTTP requests (curl, Postman, etc.)

### Test Sequence

#### Test 1: Get JWT Token
```bash
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "yenji100",
    "password": "kingjulien100"
  }'
```

**Expected response:**
```json
{
  "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
}
```

**If you get 401:** Invalid credentials. Check database for user.

---

#### Test 2: Use JWT Token to Call mcp-proxy

Copy the `access` token from Test 1 and use it:

```bash
curl -X POST http://localhost:8000/mcp-proxy/ \
  -H "Authorization: Bearer <PASTE_ACCESS_TOKEN_HERE>" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools.call",
    "params": {
      "name": "get_patient_overview",
      "arguments": {"patient_id": "SOME_PATIENT_ID"}
    }
  }'
```

**Example with full token:**
```bash
curl -X POST http://localhost:8000/mcp-proxy/ \
  -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpZCI6IjU1MGU4NDAwLWUyOWItNDFkNC1hNzE2LTQ0NjY1NTQ0MDAwMCIsImlhdCI6MTczMDcyMDAwMH0.abcdefgh..." \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools.call",
    "params": {
      "name": "get_patient_overview",
      "arguments": {"patient_id": "P001"}
    }
  }'
```

**Expected response (success):**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "patient_id": "P001",
    "name": "John Doe",
    ...
  }
}
```

**Possible responses:**

| Status | Meaning | Solution |
|--------|---------|----------|
| 200 | Success | ✅ Working! |
| 400 | Invalid JSON | Check your JSON syntax |
| 401 | No JWT token | Get token from `/api/token/` first |
| 403 | Invalid JWT token | Token expired or invalid signature |
| 502 | MCP unreachable | Check MCP server is running |

---

## Testing with Postman

### 1. Create Token Request
- **URL:** `POST http://localhost:8000/api/token/`
- **Headers:** `Content-Type: application/json`
- **Body (raw JSON):**
  ```json
  {
    "username": "yenji100",
    "password": "kingjulien100"
  }
  ```
- **Send** → Copy the `access` value

### 2. Create MCP Proxy Request
- **URL:** `POST http://localhost:8000/mcp-proxy/`
- **Headers:**
  - `Authorization: Bearer <PASTE_ACCESS_VALUE>`
  - `Content-Type: application/json`
- **Body (raw JSON):**
  ```json
  {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools.call",
    "params": {
      "name": "get_patient_overview",
      "arguments": {"patient_id": "PATIENT_ID"}
    }
  }
  ```
- **Send** → Should get 200 OK with tool result

---

## Testing with Python

```python
import requests
import json

# Step 1: Get JWT token
token_response = requests.post(
    'http://localhost:8000/api/token/',
    json={
        'username': 'yenji100',
        'password': 'kingjulien100'
    }
)

if token_response.status_code != 200:
    print(f"Failed to get token: {token_response.text}")
    exit(1)

access_token = token_response.json()['access']
print(f"✅ Got token: {access_token[:20]}...")

# Step 2: Call mcp-proxy with JWT
mcp_response = requests.post(
    'http://localhost:8000/mcp-proxy/',
    headers={
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    },
    json={
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'tools.call',
        'params': {
            'name': 'get_patient_overview',
            'arguments': {'patient_id': 'P001'}
        }
    }
)

print(f"Status: {mcp_response.status_code}")
print(f"Response: {json.dumps(mcp_response.json(), indent=2)}")
```

---

## Troubleshooting

### Error: "CSRF token missing" (Still getting 403)
**Solution:** Make sure you replaced `frontend/views.py` with the fixed version from `frontend/views_fixed.py`

Verify the decorator:
```bash
grep -n "@api_view" frontend/views.py
```
Should show: `@api_view(['POST'])` on the mcp_proxy function

### Error: "Invalid token" (401)
**Possible causes:**
1. Token has expired (8 hour lifetime)
2. Token is corrupted/incomplete
3. Using wrong JWT_SECRET

**Solution:** Get a fresh token with `/api/token/`

### Error: "MCP server unreachable" (502)
**Cause:** MCP server not running

**Solution:**
```bash
# Make sure MCP server is running
python mcp_server/main.py

# Or check if it's running on the configured port:
# Default: http://127.0.0.1:9000/mcp/
```

### Error: "Invalid JSON" (400)
**Cause:** Malformed request body

**Solution:** Check your JSON syntax. Use a JSON validator.

---

## Frontend Integration

If you have a frontend (HTML/JavaScript):

### JavaScript Example
```javascript
// Step 1: Get token
const tokenResponse = await fetch('/api/token/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    username: 'yenji100',
    password: 'kingjulien100'
  })
});

const { access } = await tokenResponse.json();

// Step 2: Use token to call mcp-proxy
const mcpResponse = await fetch('/mcp-proxy/', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    method: 'tools.call',
    params: {
      name: 'get_patient_overview',
      arguments: { patient_id: 'P001' }
    }
  })
});

const result = await mcpResponse.json();
console.log('Tool result:', result);
```

### React/Vue Integration
Store token in state and include in all API calls:
```javascript
const [token, setToken] = useState(null);

// After login
const response = await fetch('/api/token/', ...);
const { access } = await response.json();
setToken(access);

// In subsequent calls
const headers = {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json'
};
```

---

## Security Checklist

- [ ] Removed query parameter authentication (`?username=...&password=...`)
- [ ] Using Bearer token in Authorization header
- [ ] Tokens are stored securely (not in URL, localStorage for SPA)
- [ ] HTTPS enabled in production
- [ ] JWT_SECRET is environment variable (not hardcoded)
- [ ] Token expiration is set (8 hours is good)
- [ ] CSRF middleware still enabled for form-based views
- [ ] No `@csrf_exempt` on sensitive endpoints

---

## Files Modified
- ✅ `frontend/views.py` - Updated mcp_proxy to use JWT
- 📋 `frontend/views_fixed.py` - Reference implementation with full docs
- 📋 `CSRF_FIX_ANALYSIS.md` - Detailed technical analysis
- 📋 `AUTHENTICATION_FLOW.md` - Visual flow diagrams
- 📋 `CSRF_FIX_SUMMARY.md` - Quick reference

---

## Next Steps

1. **Implement the fix** - Follow Steps 1-5 above
2. **Test with curl** - Verify JWT token flow works
3. **Update frontend** - Ensure JavaScript/frontend uses JWT
4. **Monitor logs** - Check Django logs for any errors
5. **Load test** - Test with multiple concurrent requests

For questions, refer to:
- Django REST Framework JWT docs: https://django-rest-framework-simplejwt.readthedocs.io/
- CSRF/CORS: https://docs.djangoproject.com/en/5.2/topics/security/
