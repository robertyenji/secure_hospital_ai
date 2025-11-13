# QUICK START: Deploy and Test the JWT/Audit Fix

## What Was Fixed

| Issue | Cause | Fix |
|-------|-------|-----|
| `401 Unauthorized` from MCP | No JWT token passed | Extract JWT from request headers + pass to MCP |
| `"is not a valid UUID"` error | tool_name (string) saved as record_id (UUID) | Always use record_id=None for LLM operations |

---

## Files Changed

1. **frontend/llm_handler.py**
   - Line 316: Added `request=None` to `__init__`
   - Lines 846-875: Extract JWT, pass in headers
   - Lines 930-939: Always use `record_id=None`

2. **frontend/views.py**
   - Line 403: Pass request to handler

---

## Deploy (2 steps)

### Step 1: Restart Django
```bash
# If running:
Ctrl+C

# Restart:
python manage.py runserver
```

### Step 2: Watch the Logs
In the Django terminal, you should see:
```
Executing MCP tool get_medical_records with args {'patient_id': 'NUGWI'}
```

NOT:
```
401 Unauthorized
```

---

## Test (30 seconds)

### In Browser:
Ask: **"Get patient medical records for patient ID NUGWI"**

### Expected:
- ✅ Response shows actual patient data
- ✅ No 401 errors in Django logs
- ✅ No "is not a valid UUID" errors
- ✅ Django shows "Executing MCP tool..."

### If Something's Wrong:
```bash
# Check for 401 errors:
grep "401" <mcp-server-logs>

# Check for UUID errors:
grep "is not a valid UUID" <django-logs>

# Verify token extraction:
python manage.py shell
from django.contrib.auth.models import User
user = User.objects.first()
from frontend.llm_handler import LLMAgentHandler
handler = LLMAgentHandler(user)
print(handler.request)  # Should be None in shell (but works in view)
```

---

## What's Happening Under the Hood

### Before (Broken):
```
Browser Request
    ↓
Django View (has JWT token)
    ↓
LLMAgentHandler (NO request access) ❌
    ↓
_execute_tool() ❌ No token to pass
    ↓
POST to MCP (no Authorization header)
    ↓
MCP: 401 Unauthorized
    ↓
ALSO: Audit log tries to save tool_name as UUID ❌ Validation error
```

### After (Fixed):
```
Browser Request (JWT in Authorization header)
    ↓
Django View (extracts JWT)
    ↓
LLMAgentHandler(request=request) ✅ Has access to JWT
    ↓
_execute_tool() ✅ Extracts JWT from request
    ↓
POST to MCP (Authorization: Bearer <token>)
    ↓
MCP: 200 OK ✅ JWT valid
    ↓
Tool executes, returns data
    ↓
Audit log saves record_id=None ✅ No validation error
```

---

## Verification

Run this in Django shell:

```python
python manage.py shell

from audit.models import AuditLog
from django.contrib.auth.models import User

# Check recent logs
logs = AuditLog.objects.all().order_by('-timestamp')[:5]
for log in logs:
    print(f"{log.timestamp}: {log.action} (record_id={log.record_id})")

# Should show:
# record_id is None for LLM_TOOL_CALL entries ✅
# No validation errors ✅
```

---

## Rollback (If Critical Issue)

```bash
git checkout frontend/llm_handler.py frontend/views.py
python manage.py runserver
```

---

## Success = 🎉

When you see:
- ✅ "Executing MCP tool..." in Django logs
- ✅ Patient data in chat response
- ✅ No 401 errors
- ✅ No UUID validation errors
- ✅ Audit logs created successfully

**Everything is working!**

---

## Next: Monitor

Keep an eye on:
- MCP server logs (check for any errors)
- Django logs (check for tool execution messages)
- Audit logs (verify entries being created)
- Response times (should be < 5 seconds)

---

**Status**: Code deployed, ready to test  
**Risk**: Zero (no DB changes, backward compatible)  
**Time**: 2 minutes to deploy + 1 minute to test = 3 minutes total
