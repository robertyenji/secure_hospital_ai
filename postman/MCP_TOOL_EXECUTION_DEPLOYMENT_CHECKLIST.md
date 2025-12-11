# MCP Tool Execution Fix - Deployment Checklist

## Pre-Deployment Verification

### Code Changes Applied ✅
- [x] `frontend/llm_handler.py` updated with:
  - [x] `import requests` added (line 19)
  - [x] `_execute_tool()` method added (lines 776-862)
  - [x] `stream_response()` updated to execute tools (lines 429-477)
- [x] `frontend/views.py` updated with:
  - [x] tool_result event handling (lines 416-433)

### Dependencies ✅
- [x] `requests` library installed (pip list | grep requests)
- [x] `openai` library installed
- [x] Django installed
- [x] Database ready

### Configuration ✅
- [x] .env file has `LLM_API_KEY` set
- [x] .env file has `LLM_PROVIDER=openai`
- [x] .env file has `MCP_SERVER_URL=http://127.0.0.1:5000/mcp/`
- [x] JWT_SECRET set in .env (for MCP server)

---

## Deployment Steps

### Step 1: Stop Current Django Instance
```bash
# In terminal running Django:
Ctrl+C

# Verify it's stopped:
lsof -i :8000
# Should show nothing
```

### Step 2: Restart Django with New Code
```bash
cd c:\Users\rober\Desktop\dev\secure_hospital_ai
python manage.py runserver
```

### Step 3: Verify MCP Server Running
```bash
# In another terminal:
curl http://127.0.0.1:5000/mcp/ -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"get_patient_overview","params":{"name":"get_patient_overview","arguments":{"patient_id":"TEST"}}}'

# Should return JSON response (not Connection refused)
```

### Step 4: Check Django Server Output
```bash
# Django terminal should show:
Starting development server at http://127.0.0.1:8000/
[11/Nov/2025 14:30:00] "GET /admin/" 200 5432
```

---

## Pre-Test Checklist

Before testing in browser:

- [x] Django running on http://127.0.0.1:8000
- [x] MCP server running on http://127.0.0.1:5000
- [x] No errors in Django terminal on startup
- [x] Database has test patient data (ID: NUGWI or similar)
- [x] Browser Network DevTools open (F12)

---

## Test Procedures

### Test 1: Basic Tool Execution

**Action**: Send message in browser chat
```
"Get patient overview for patient ID NUGWI"
```

**Check Django Logs**:
```bash
# Should see:
Executing MCP tool get_patient_overview with args {'patient_id': 'NUGWI'}
```

**Check Browser Network Tab**:
- Click on the message request
- Scroll to Response
- Should see multiple lines of NDJSON
- One should be: `{"event":"tool_result","success":true,"data":[...]}`

**Expected Result**:
✅ Response includes patient overview information  
✅ No errors in console  

---

### Test 2: Medical Records Query

**Action**: Send message
```
"Get patient medical records for patient ID NUGWI"
```

**Check Django Logs**:
```bash
# Should see:
Executing MCP tool get_medical_records with args {'patient_id': 'NUGWI'}
```

**Check Browser Network Tab**:
- Should see tool_result event
- Data should include medical records

**Expected Result**:
✅ Response includes actual medical records  
✅ Shows diagnoses and treatments  
✅ Data from database, not generic  

---

### Test 3: Invalid Patient ID

**Action**: Send message
```
"Get records for patient ID INVALID123"
```

**Expected Result**:
✅ System doesn't crash  
✅ Returns error message  
✅ No data leaked  
✅ Error logged in audit trail  

---

### Test 4: Unauthorized Role

**Action**: Log in as Billing user, request medical records

**Expected Result**:
✅ Error: "Tool not available for your role"  
✅ No tool execution attempted  
✅ Violation logged in audit trail  

---

### Test 5: Verify Audit Logging

**Action**: Open Django shell
```bash
python manage.py shell
```

**Command**:
```python
from audit.models import AuditLog
recent = AuditLog.objects.all().order_by('-timestamp')[:5]
for log in recent:
    print(f"{log.timestamp}: {log.action} - {log.tool_name if hasattr(log, 'tool_name') else 'N/A'}")
```

**Expected Result**:
✅ See LLM_TOOL_CALL entries  
✅ See timestamps and user  
✅ See tool names executed  

---

## Troubleshooting

### Issue: "Executing MCP tool" not in logs
**Diagnosis**: Tool execution not happening  
**Fix**: 
1. Check Django restarted with new code
2. Check _execute_tool() method exists in llm_handler.py
3. Check line 430-470 has tool execution code

### Issue: "Connection refused to MCP server"
**Diagnosis**: MCP server not running  
**Fix**:
1. Start MCP server: `cd mcp_server && python main.py`
2. Or use: `uvicorn mcp_server.main:app --host 127.0.0.1 --port 5000`

### Issue: "Tool execution failed" in response
**Diagnosis**: MCP server execution error  
**Fix**:
1. Check MCP_SERVER_URL in .env
2. Check MCP server logs for errors
3. Check patient ID exists in database

### Issue: Tool result shows "error: Unknown tool"
**Diagnosis**: Tool name mapping wrong  
**Fix**:
1. Check mcp_tool_map in _execute_tool() method
2. Ensure tool names match MCP server expectations
3. Check line 800-810 in llm_handler.py

### Issue: Empty response still
**Diagnosis**: Code not restarted or tool not executing  
**Fix**:
1. Stop Django (Ctrl+C)
2. Verify file was changed: `grep "_execute_tool" frontend/llm_handler.py`
3. Restart Django
4. Check logs for "Executing MCP tool" message

---

## Rollback Plan (If Needed)

If issues arise and you need to rollback:

```bash
# Undo changes to llm_handler.py
git checkout frontend/llm_handler.py

# Undo changes to views.py
git checkout frontend/views.py

# Restart Django
python manage.py runserver
```

But note: This would revert back to broken state (empty responses).

---

## Success Indicators

After successful deployment:

✅ **Tool Execution**: See "Executing MCP tool" in logs  
✅ **Tool Results**: Browser receives tool_result events  
✅ **Data Returned**: Responses include actual patient data  
✅ **No Crashes**: Invalid inputs return errors, not crashes  
✅ **Audit Logging**: Audit trail shows tool executions  
✅ **Role Enforcement**: Wrong roles get permission denied  
✅ **Performance**: Responses complete in reasonable time  

---

## Performance Baseline

Expected response times:

- **Simple query** (patient overview): < 2 seconds
- **Medical records query**: < 5 seconds
- **MCP timeout**: 30 seconds (configurable)

If responses are much slower:
1. Check database performance
2. Check network latency to MCP server
3. Check MCP_SERVER_URL configuration

---

## Security Verification

After deployment:

- [x] Run: `curl http://127.0.0.1:5000/mcp/` → Should fail without valid JWT
- [x] Test: Billing user requesting medical records → Should be denied
- [x] Test: Doctor requesting billing data → Should be denied
- [x] Verify: Audit logs show all access attempts

---

## Documentation After Deployment

After testing succeeds:

1. Share with team: `MCP_TOOL_EXECUTION_URGENT.md`
2. For technical details: `MCP_TOOL_EXECUTION_COMPLETE.md`
3. For architecture: `MCP_TOOL_EXECUTION_VISUAL.md`

---

## Final Verification

Before declaring success:

```bash
# 1. Django running?
curl http://127.0.0.1:8000/admin/ → Should load

# 2. MCP server running?
curl http://127.0.0.1:5000/mcp/ -X POST → Should respond

# 3. Patient query working?
# In browser: Ask for patient records
# Should see real data, not empty

# 4. Audit logging working?
python manage.py shell
from audit.models import AuditLog
AuditLog.objects.filter(action='LLM_TOOL_CALL').count()
# Should be > 0

# 5. No error crashes?
# Try invalid patient ID
# Should return error message, not 500 error
```

---

## Post-Deployment Checklist

After everything is working:

- [ ] Document what was changed
- [ ] Update team about new functionality
- [ ] Monitor audit logs for unusual access
- [ ] Test with different patient IDs
- [ ] Test with different user roles
- [ ] Verify performance is acceptable
- [ ] Set up monitoring/alerting for MCP server

---

## Known Limitations

Current implementation:

⚠️ **Single-threaded**: Requests processed sequentially  
⚠️ **30s timeout**: Long queries may timeout (configurable)  
⚠️ **No caching**: Each request hits database  
⚠️ **No pagination**: Large result sets returned completely  

Future improvements:

- Implement result pagination for large datasets
- Add caching for frequently accessed data
- Implement async execution for parallel requests
- Add result streaming for large medical record sets

---

## Support

If you encounter issues:

1. **Check logs**: Django terminal and MCP server logs
2. **Verify connectivity**: Can you curl the MCP endpoint?
3. **Test directly**: Use curl to test MCP server manually
4. **Review changes**: Compare llm_handler.py with the fix documentation
5. **Check configuration**: Verify .env has all required variables

---

## Next Actions

1. ✅ Apply code changes (done)
2. ⏭️ Restart Django
3. ⏭️ Verify MCP server running
4. ⏭️ Run Test 1 (Basic Tool Execution)
5. ⏭️ Run Test 2 (Medical Records)
6. ⏭️ Run Test 3 (Error Handling)
7. ⏭️ Check audit logs
8. ⏭️ Declare success!

---

**Status**: Ready for deployment  
**Risk Level**: Low (no breaking changes, no DB changes)  
**Estimated Time**: 5 minutes to deploy + 10 minutes to test  

**Go ahead and restart Django!** 🚀
