# 🎯 DEPLOYMENT CHECKLIST - JWT Fix

## Pre-Deployment Verification

### ✅ Code Changes Applied
- [x] `frontend/llm_handler.py` modified
  - [x] `import jwt` added (line 19)
  - [x] `_execute_tool()` generates JWT token (lines 840-887)
  - [x] Token includes user_id, role, username
  - [x] Token signed with JWT_SECRET + JWT_ALG
  - [x] Token passed in Authorization header

### ✅ Syntax Verified
- [x] No syntax errors in llm_handler.py
- [x] JWT library imported correctly
- [x] All required variables defined

### ✅ Configuration Ready
- [x] `.env` has `JWT_SECRET` set
- [x] `.env` has `JWT_ALG=HS256`
- [x] `.env` has `MCP_SERVER_URL=http://127.0.0.1:5000/mcp/`
- [x] MCP server has same JWT_SECRET

---

## Deployment Steps (Copy & Paste)

### Step 1: Verify Configuration
```bash
# Check JWT_SECRET is set
echo "JWT_SECRET=$JWT_SECRET"

# Should print: JWT_SECRET=your-secret-key
# If blank, add to .env and restart terminal
```

### Step 2: Stop Django (if running)
```bash
# In the terminal running Django:
Ctrl+C

# Should show: "Keyboard interrupt received"
```

### Step 3: Verify Code Change
```bash
# Verify jwt import exists
grep "import jwt" frontend/llm_handler.py

# Should output: import jwt
```

### Step 4: Start Django
```bash
python manage.py runserver
```

**Should see**:
```
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

### Step 5: Verify MCP Server
```bash
# In another terminal:
curl http://127.0.0.1:5000/mcp/ -X OPTIONS

# Should respond (even if error, that's OK - means it's running)
# If "Connection refused", MCP server not running
```

---

## Testing Procedure

### Test 1: Simple Patient Query (30 seconds)

**In Browser**:
1. Open http://127.0.0.1:8000/
2. Navigate to chat
3. Ask: `"Get patient medical records for patient ID NUGWI"`

**Expected Result**:
- Chat shows patient information
- NOT empty
- NOT error message

**Check Django Logs** (watch the terminal running Django):
```
Should see:
  Executing MCP tool get_medical_records with args {'patient_id': 'NUGWI'}
  
Should NOT see:
  401 Unauthorized
  is not a valid UUID
  Missing Authorization token
```

### Test 2: Verify No Errors (1 minute)

**In Django Terminal**:
```bash
# Search for errors:
grep -i "401" <output>
grep -i "unauthorized" <output>
grep -i "error" <output>

# Should find nothing (or only old errors from before restart)
```

**In Browser Console** (F12 → Console):
- Should see no JavaScript errors
- Network tab should show successful responses

### Test 3: Verify Token Creation (2 minutes)

**In Terminal**:
```bash
python manage.py shell

# Import what we need
from django.contrib.auth.models import User
from frontend.llm_handler import LLMAgentHandler
import os

# Get a user
user = User.objects.first()

# Create handler (like views do)
handler = LLMAgentHandler(user)

# Test tool execution
result = handler._execute_tool("get_patient_records", {"patient_id": "NUGWI"})

# Check result
print(f"Success: {result['success']}")
print(f"Error: {result['error']}")
if result['data']:
    print(f"Data records: {len(result['data'])}")
```

**Expected Output**:
```
Success: True
Error: None
Data records: 2
```

NOT:
```
Success: False
Error: MCP server returned 401: ...
```

---

## Troubleshooting Decision Tree

```
                    ┌─────────────────────┐
                    │ Getting 401 errors? │
                    └──────────┬──────────┘
                               │
               ┌───────────────┴───────────────┐
               │                               │
               ▼                               ▼
    ┌──────────────────────┐      ┌──────────────────────┐
    │ Check JWT_SECRET     │      │ Check MCP running    │
    │ is set in .env       │      │ on port 5000         │
    └──────────┬───────────┘      └──────────┬───────────┘
               │                              │
        ┌──────▼──────┐              ┌──────▼──────┐
        │ Not set? ❌  │              │ Not running?│
        └──────┬──────┘              └──────┬──────┘
               │                            │
               ▼                            ▼
        Add to .env             Start MCP:
        JWT_SECRET=...          uvicorn mcp_server.main:app \
        Restart Django          --host 127.0.0.1 --port 5000
        
        Then test again         Then test again
               │                            │
               └────────────┬───────────────┘
                            │
                    Still getting 401?
                            │
               ┌────────────▼────────────┐
               │ Check MCP has same      │
               │ JWT_SECRET              │
               │                         │
               │ If MCP runs separately: │
               │ - Check its .env        │
               │ - Must match Django     │
               │ - Restart MCP           │
               │                         │
               │ If MCP in same process: │
               │ - Restart Django        │
               │ - Reload environment    │
               └────────────┬────────────┘
                            │
                    Test again in browser
                            │
               ┌────────────▼────────────┐
               │ Still 401? Contact:     │
               │ - Check MCP logs        │
               │ - Check JWT library     │
               │ - Verify Python version │
               └────────────────────────┘
```

---

## Success Checklist

Before declaring success, verify ALL:

- [ ] Django running: `curl http://127.0.0.1:8000/` → 200 OK
- [ ] MCP running: `curl http://127.0.0.1:5000/mcp/ -X OPTIONS` → response
- [ ] No Django errors: Check terminal for 500 errors
- [ ] Chat sends message: Browser shows message in chat
- [ ] Django logs show execution: "Executing MCP tool..."
- [ ] No 401 errors: Search Django logs - should be none
- [ ] Response has data: Chat shows actual patient information
- [ ] Audit log has entries: Check database for new logs
- [ ] User can ask multiple questions: Test 2-3 different queries

---

## Common Issues & Fixes

### Issue: Still Getting 401
**Cause**: JWT_SECRET not matching between Django and MCP

**Fix**:
1. Print current secret: `python -c "import os; print(os.getenv('JWT_SECRET'))"`
2. Verify MCP has same secret
3. If different, update one to match the other
4. Restart BOTH services
5. Test again

### Issue: "JWT_SECRET not configured"
**Cause**: Environment variable not set

**Fix**:
1. Add to .env: `JWT_SECRET=your-secret-key`
2. Restart Django: `Ctrl+C` then `python manage.py runserver`
3. Test again

### Issue: "No module named jwt"
**Cause**: PyJWT library not installed

**Fix**:
```bash
pip install PyJWT
python manage.py runserver
```

### Issue: MCP server shows "400 Bad Request"
**Cause**: Malformed JSON in request

**Fix**:
1. Check request payload is valid JSON
2. Check all required fields present
3. Restart MCP server
4. Test again

### Issue: Response is empty or None
**Cause**: Tool executed but returned no data

**Possible causes**:
1. Patient ID doesn't exist in database
2. Tool query returned empty result
3. Redaction removed all data (PHI restriction)

**Fix**:
1. Verify patient ID exists: `SELECT * FROM patient WHERE id='NUGWI';`
2. Check role has access to medical records
3. Try different patient ID
4. Check MCP logs for details

---

## Monitoring After Deployment

### Watch These Logs

**Django Terminal**:
```bash
# Look for these patterns:
- "Executing MCP tool" = Good ✅
- "401" = Bad ❌
- "error" = Investigate
- "Tool execution successful" = Good ✅
```

**Browser Network Tab** (F12):
```
Look for requests to:
- /api/chat/message/ → should be 200 or 201
- Check Response → should have actual data
```

### Test Queries to Try

1. "Get patient overview for patient ID NUGWI"
2. "What are the appointments for patient NUGWI?"
3. "Show me the admissions for patient ID NUGWI"
4. "Get medical records for patient NUGWI"

All should return actual data from database.

---

## Performance Expectations

**Expected Response Times**:
- Simple query (patient overview): 1-2 seconds
- Complex query (medical records): 2-5 seconds
- Maximum timeout: 30 seconds

**If slower than expected**:
1. Check database performance: `EXPLAIN ANALYZE SELECT ...`
2. Check network latency: `ping 127.0.0.1:5000`
3. Check if other processes slowing system

---

## Rollback Plan (If Critical Issue)

```bash
# If system completely broken:

# Revert code
git checkout frontend/llm_handler.py

# Remove jwt import (or install library)
pip install PyJWT

# Restart Django
python manage.py runserver

# You're back to previous state (but still has 401 errors)
```

---

## Final Sign-Off

When you complete deployment and all tests pass:

- ✅ Code deployed
- ✅ Django restarted
- ✅ MCP running
- ✅ No 401 errors
- ✅ Chat returns patient data
- ✅ Audit logs created
- ✅ Multiple queries tested

**You're done!** 🎉

The system now successfully:
1. ✅ Creates JWT tokens for authentication
2. ✅ Passes tokens to MCP server
3. ✅ MCP server validates and executes tools
4. ✅ Patient data returned to LLM
5. ✅ Chat shows actual information

---

## Next Steps (After Success)

1. **Load Test**: Try with multiple users simultaneously
2. **Data Validation**: Verify accuracy of returned data
3. **Role Testing**: Test with different user roles (Doctor, Nurse, Billing)
4. **Audit Review**: Examine audit logs for completeness
5. **Documentation**: Update system docs with JWT flow
6. **Security Review**: Consider additional token refresh/expiration
7. **Production**: Harden JWT_SECRET for production environment

---

**Status**: Ready to Deploy ✅  
**Estimated Time**: 5 minutes  
**Risk Level**: Very Low  
**Go!** 🚀
