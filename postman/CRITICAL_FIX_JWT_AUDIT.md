# CRITICAL FIX: JWT Token and Audit Logging

## Issues Fixed

### Issue 1: 401 Unauthorized from MCP Server
**Symptom**: `INFO: 127.0.0.1:49682 - "POST /mcp/ HTTP/1.1" 401 Unauthorized`

**Root Cause**: JWT token was NOT being passed to MCP server in Authorization header

**Fix Applied**: 
- Modified `_execute_tool()` to extract JWT token from Django request
- Extracts from `Authorization: Bearer <token>` header
- Passes token in request headers to MCP server
- Line 850-863 in llm_handler.py

**Code Change**:
```python
# Extract JWT token from request Authorization header
jwt_token = None
if self.request:
    auth_header = self.request.META.get('HTTP_AUTHORIZATION', '')
    if auth_header.startswith('Bearer '):
        jwt_token = auth_header[7:]  # Remove 'Bearer ' prefix

# Prepare headers with JWT token for MCP server
headers = {
    "Content-Type": "application/json",
}
if jwt_token:
    headers["Authorization"] = f"Bearer {jwt_token}"
```

---

### Issue 2: UUID Validation Error in Audit Log
**Symptom**: `django.core.exceptions.ValidationError: ['"get_patient_records" is not a valid UUID.']`

**Root Cause**: Code was trying to store tool name (string) as record_id (UUID field)

**Previous Fix Attempt**: Conditional: `record_id = tool_name if tool_name else None` 
- This was still passing the string to the database
- UUID field validation caught it and rejected it

**Correct Fix Applied**:
- ALWAYS set `record_id = None` for LLM operations
- LLM operations don't have a specific database record to reference
- Only use record_id when logging actual database record access
- Line 930-939 in llm_handler.py

**Code Change**:
```python
def _log_audit(self, action: str, table_name: str, 
               tool_name: str = None, is_phi: bool = False):
    try:
        # IMPORTANT: Do NOT use tool_name as record_id
        # tool_name is a string and record_id must be a UUID
        # Always pass None for record_id unless it's an actual database record ID
        
        self.AuditLog.objects.create(
            user=self.user,
            action=action,
            table_name=table_name,
            record_id=None,  # Always None for LLM operations
            ip_address=self.ip_address,
            is_phi_access=is_phi
        )
```

---

## Files Modified

### 1. frontend/llm_handler.py
**Line 316**: Added `request=None` parameter to `__init__`
```python
def __init__(self, user: User, ip_address: str = "", request=None):
    ...
    self.request = request
```

**Lines 850-863**: Updated `_execute_tool()` to extract and pass JWT token
- Extract JWT from Authorization header
- Pass token in request headers
- Removed placeholder comment

**Lines 930-939**: Fixed `_log_audit()` to always use `record_id=None`
- Removed conditional logic
- Always pass None (correct for LLM operations)
- Added clear documentation

### 2. frontend/views.py
**Line 403**: Updated LLMAgentHandler initialization to pass request
```python
llm_handler = LLMAgentHandler(request.user, request=request)
```

---

## How It Works Now

### JWT Authentication Flow:
```
1. User logs in → Django JWT created → Sent in Authorization header
2. User sends chat message → Request includes JWT token
3. Django handler extracts token from Authorization header
4. Token passed to LLMAgentHandler via request parameter
5. _execute_tool() reads token from request
6. Token included in POST to MCP server
7. MCP server validates JWT → 200 OK (not 401)
8. MCP server executes tool with proper authentication
```

### Audit Logging Flow:
```
1. LLM makes tool call
2. Django calls _log_audit(action='LLM_TOOL_CALL', ...)
3. No record_id passed (it's None by default)
4. AuditLog.objects.create(..., record_id=None, ...)
5. Database accepts None (it's nullable)
6. No UUID validation error
7. Audit entry created successfully
```

---

## Testing These Fixes

### Test 1: JWT Token Being Passed
```bash
# Watch MCP server logs - should see valid JWT
# Check for successful tool execution (not 401 errors)
curl -v http://127.0.0.1:5000/mcp/
# Should show: 401 Unauthorized (because no token in curl)

# But in Django chat:
# Should NOT show 401 errors
# Should show successful tool execution
```

### Test 2: Audit Log Creation
```bash
python manage.py shell
from audit.models import AuditLog

# Check recent audit logs
recent = AuditLog.objects.all().order_by('-timestamp')[:10]
for log in recent:
    print(f"{log.timestamp}: {log.action}, record_id={log.record_id}")

# Should show:
# record_id=None for LLM_TOOL_CALL entries (not validation errors)
```

### Test 3: End-to-End Chat Flow
```
1. In browser: "Get patient medical records for patient ID NUGWI"
2. Check Django logs for "Executing MCP tool get_medical_records"
3. Check MCP server logs for successful execution (not 401)
4. Response should include actual patient data
5. Check audit log - should have no validation errors
```

---

## Verification Checklist

After deploying:

- [ ] Django restarted with new code
- [ ] MCP server running on port 5000
- [ ] No "401 Unauthorized" in MCP server logs
- [ ] No "is not a valid UUID" validation errors
- [ ] Chat query returns patient data (not empty)
- [ ] Audit logs created successfully
- [ ] AuditLog.record_id is None for LLM operations

---

## Key Learnings

1. **JWT Token Handling**:
   - MCP server requires valid JWT for authentication
   - Token must be extracted from incoming request
   - Must be passed in Authorization header with "Bearer " prefix

2. **Audit Record IDs**:
   - Only use record_id for actual database record references
   - LLM operations don't have specific records to reference
   - Always use None for non-record-specific operations
   - Prevents UUID validation errors

3. **Request Context**:
   - Need to pass request object to handler to access headers
   - Request.META contains all HTTP headers (uppercase with HTTP_ prefix)
   - Must parse Authorization header to extract token

---

## Deployment Steps

1. **Stop Django**:
   ```bash
   Ctrl+C
   ```

2. **Deploy Changes**:
   - Files already modified: llm_handler.py and views.py
   - No database migrations needed
   - No configuration changes needed

3. **Restart Django**:
   ```bash
   python manage.py runserver
   ```

4. **Verify MCP Server**:
   ```bash
   # In another terminal
   curl http://127.0.0.1:5000/mcp/ -X POST
   # Should respond (even with 401 for test, that's normal)
   ```

5. **Test in Browser**:
   - Ask: "Get patient medical records for patient ID NUGWI"
   - Check response (should have data, not empty)
   - Check Django logs (should see "Executing MCP tool")
   - Check audit logs (should have successful entries)

---

## Success Criteria

✅ No "401 Unauthorized" errors in MCP logs  
✅ No "is not a valid UUID" validation errors  
✅ Tool calls successfully execute (see "Executing MCP tool" in logs)  
✅ Patient data returned in responses  
✅ Audit logs created without errors  
✅ Chat interface shows actual patient information  

---

## Rollback (If Needed)

If issues arise:

```bash
# Revert changes
git checkout frontend/llm_handler.py frontend/views.py

# Restart Django
python manage.py runserver
```

But these fixes are critical - should not need rollback.

---

**Status**: ✅ Ready to Deploy  
**Risk**: Low (no DB changes, backward compatible)  
**Testing Time**: 5 minutes  
