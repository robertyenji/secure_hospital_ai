# MCP Tool Execution - Visual Guide

## The Problem (Before Fix)

```
┌─────────────────────────────────────────────────────────────┐
│ USER ASKS: "Get patient medical records for NUGWI"         │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │ LLM receives available tools │
        │ - get_patient_overview      │
        │ - get_patient_records       │  ◄─── Available in schema
        │ - get_patient_admissions    │
        │ - get_patient_appointments  │
        │ - get_my_shifts             │
        └─────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ LLM analyzes: "User wants        │
        │ medical records for patient      │
        │ NUGWI"                           │
        │                                  │
        │ LLM decision: Call                │
        │ get_patient_records(             │
        │   patient_id="NUGWI"             │
        │ )                                │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ Django validates RBAC:           │
        │ Is tool_name not None? ✓         │
        │ Is Doctor allowed? ✓             │
        │ ✓ VALIDATION PASSES              │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ Tool call logged to audit        │
        │ ✓ LOGGING COMPLETE               │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ Tool call emitted to frontend    │
        │ ✓ EVENT EMITTED                  │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ ❌ BUT TOOL NOT EXECUTED!       │
        │ ❌ Database not queried          │
        │ ❌ No data retrieved             │
        │ ❌ LLM has no data to use        │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ LLM responds:                    │
        │ "I don't have access to that     │
        │ information" or empty response   │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ USER SEES: Empty/generic reply   │
        │ ❌ PROBLEM!                      │
        └──────────────────────────────────┘
```

---

## The Solution (After Fix)

```
┌─────────────────────────────────────────────────────────────┐
│ USER ASKS: "Get patient medical records for NUGWI"         │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │ LLM receives available tools │
        │ - get_patient_overview      │
        │ - get_patient_records       │  ◄─── Available in schema
        │ - get_patient_admissions    │
        │ - get_patient_appointments  │
        │ - get_my_shifts             │
        └─────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ LLM decides:                     │
        │ Call get_patient_records(        │
        │   patient_id="NUGWI"             │
        │ )                                │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ Django validates RBAC:           │
        │ ✓ VALIDATION PASSES              │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ ✅ NEW: EXECUTE TOOL!            │
        │                                  │
        │ _execute_tool(                   │
        │   "get_patient_records",         │
        │   {"patient_id": "NUGWI"}        │
        │ )                                │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ Call MCP Server                  │
        │ POST /mcp/                       │
        │ {                                │
        │   "method": "get_medical_records"│
        │   "params": {                    │
        │     "arguments": {               │
        │       "patient_id": "NUGWI"      │
        │     }                            │
        │   }                              │
        │ }                                │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ MCP Server:                      │
        │ 1. Validates JWT                 │
        │ 2. Checks RBAC (again!)          │
        │ 3. Queries database:             │
        │    SELECT * FROM                 │
        │    medical_records               │
        │    WHERE patient_id='NUGWI'      │
        │ 4. Redacts PHI                   │
        │ 5. Returns data                  │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ Return tool result:              │
        │ {                                │
        │   "success": true,               │
        │   "data": [                      │
        │     {                            │
        │       "diagnosis": "Hypertension"│
        │       "treatment": "Lisinopril"  │
        │     },                           │
        │     {                            │
        │       "diagnosis": "Type 2 Diab..│
        │       "treatment": "Metformin"   │
        │     }                            │
        │   ]                              │
        │ }                                │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ Tool call logged to audit        │
        │ ✓ LOGGING COMPLETE               │
        │ (is_phi_access=true)             │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ Emit tool_result to frontend     │
        │ ✓ EVENT EMITTED WITH DATA        │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ Add data to LLM context:         │
        │ [Tool Result: get_patient_...    │
        │  [{diagnosis: Hypertension...}]  │
        │                                  │
        │ ✓ DATA ADDED TO CONTEXT          │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ LLM continues with REAL DATA:    │
        │ "Patient NUGWI has               │
        │ Hypertension treated with        │
        │ Lisinopril and Type 2 Diabetes   │
        │ treated with Metformin..."       │
        │                                  │
        │ ✓ RESPONSE USES ACTUAL DATA      │
        └──────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────────────┐
        │ USER SEES: Detailed response     │
        │ with actual patient information  │
        │ ✓ SUCCESS!                       │
        └──────────────────────────────────┘
```

---

## The Three Security Layers (With Execution)

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 1: INSTRUCTION LAYER                                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  System Prompt tells LLM:                                   │
│  "You have these tools available:                           │
│   - get_patient_overview                                   │
│   - get_patient_records                                    │
│   - get_patient_admissions                                 │
│                                                              │
│   You CANNOT:                                               │
│   - Access billing information                              │
│   - Access staff records"                                   │
│                                                              │
│  If LLM follows instructions: ✓ Good                         │
│  If LLM ignores instructions: → Continue to Layer 2         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ LAYER 2: FUNCTION DEFINITION LAYER                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  LLM only receives these tool definitions:                  │
│  • get_patient_overview (available)                         │
│  • get_patient_records (available)                          │
│  • get_patient_admissions (available)                       │
│                                                              │
│  NOT in the list:                                           │
│  • get_insurance_data (missing entirely!)                   │
│  • get_staff_roster (missing entirely!)                     │
│                                                              │
│  LLM cannot call undefined tools: ✓ Safe                     │
│  (Can't call what it doesn't have)                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ LAYER 3: RUNTIME VALIDATION LAYER                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Even if LLM somehow tries get_insurance_data:              │
│                                                              │
│  _validate_tool_call() checks:                              │
│  1. Is tool_name not None? ✓ YES                            │
│  2. Is tool in whitelist? ✗ NO → PermissionDenied           │
│  → Emit error: "Not available for your role"                │
│  → Log RBAC_VIOLATION                                       │
│  → Do NOT execute tool                                      │
│                                                              │
│  Execution never happens: ✓ Safe                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│ LAYER 4: MCP SERVER RBAC LAYER (BONUS)                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Even if Django somehow lets wrong tool through:            │
│                                                              │
│  MCP Server receives request:                               │
│  1. Validates JWT token                                     │
│  2. Extracts user role from token                           │
│  3. Checks: Can this role access this resource?             │
│  4. If NO → Return 403 Forbidden                            │
│  → No data returned                                         │
│  → Access logged as denied                                  │
│                                                              │
│  Defense in depth: ✓ Layered                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Actual Execution Flow

```
┌──────────────────────────────────────────────┐
│ Browser                                      │
│ User: "Get medical records for NUGWI"       │
└────────────────────┬─────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────┐
│ REST API (Django)                            │
│ POST /api/chat/message/                      │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ OpenAI LLM                                   │
│ Receives tools in schema                     │
│ Analyzes query                               │
│ Decides: Call get_patient_records            │
│ Generates: Tool call with args               │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ LLM Handler (llm_handler.py)                 │
│                                              │
│ stream_response():                           │
│ 1. Receive tool call from LLM                │
│ 2. Extract: tool_name, arguments             │
│ 3. Validate: _validate_tool_call()           │
│    → Check RBAC whitelist                    │
│    → If not allowed: emit error              │
│    → If allowed: continue                    │
│ 4. EXECUTE: _execute_tool()                  │
│    → This is NEW!                            │
│    → Map LLM name to MCP name                │
│    → Construct JSON-RPC request              │
│    → POST to MCP server                      │
│ 5. Receive: tool_result with data            │
│ 6. Emit: tool_result event to frontend       │
│ 7. Add: data to accumulated_content          │
│ 8. LLM continues: generating response        │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ MCP Server (mcp_server/main.py)              │
│                                              │
│ 1. Receive JSON-RPC request                  │
│ 2. Validate JWT token from request           │
│ 3. Extract user role from JWT                │
│ 4. Check RBAC:                               │
│    is_allowed(MedicalRecord, read, role)     │
│ 5. Query database:                           │
│    SELECT * FROM medical_records             │
│    WHERE patient_id='NUGWI'                  │
│ 6. Redact PHI:                               │
│    Remove sensitive fields as configured     │
│ 7. Return JSON-RPC response                  │
│    with data array                           │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ Database (PostgreSQL)                        │
│                                              │
│ Query: Medical records for NUGWI             │
│ Result: [                                    │
│   {                                          │
│     id: 1,                                   │
│     diagnosis: "Hypertension",               │
│     treatment: "Lisinopril 10mg daily",      │
│     date: "2025-11-10"                       │
│   },                                         │
│   {                                          │
│     id: 2,                                   │
│     diagnosis: "Type 2 Diabetes",            │
│     treatment: "Metformin 500mg BID",        │
│     date: "2025-11-09"                       │
│   }                                          │
│ ]                                            │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ MCP Server Response                          │
│                                              │
│ {                                            │
│   "jsonrpc": "2.0",                          │
│   "id": 1,                                   │
│   "result": {                                │
│     "data": [                                │
│       {diagnosis: "Hypertension", ...},      │
│       {diagnosis: "Type 2 Diabetes", ...}    │
│     ]                                        │
│   }                                          │
│ }                                            │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ LLM Handler                                  │
│                                              │
│ receive_tool_result():                       │
│ 1. Parse response.json()                     │
│ 2. Extract: data array                       │
│ 3. Emit: tool_result event                   │
│ 4. Add: data to accumulated_content          │
│ 5. Log: LLM_TOOL_CALL audit entry            │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ OpenAI LLM (Continues)                       │
│                                              │
│ Receives:                                    │
│ [Tool Result: get_patient_records]           │
│ [                                            │
│   {                                          │
│     "diagnosis": "Hypertension",             │
│     "treatment": "Lisinopril 10mg daily",    │
│     "date": "2025-11-10"                     │
│   },                                         │
│   ...                                        │
│ ]                                            │
│                                              │
│ Generates response:                          │
│ "Patient NUGWI's medical records show        │
│  Hypertension managed with Lisinopril        │
│  and Type 2 Diabetes managed with            │
│  Metformin..."                               │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ Frontend                                     │
│ Receives NDJSON stream:                      │
│ {"type":"tool_result","success":true,...}    │
│ {"event":"token","delta":"Patient..."}       │
│ {"event":"token","delta":" NUGWI's..."}      │
│ ... more tokens ...                          │
│ {"event":"done","message_id":456}            │
│                                              │
│ Displays to user                             │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────┐
│ Browser                                      │
│                                              │
│ USER SEES:                                   │
│ "Patient NUGWI's medical records show        │
│  Hypertension managed with Lisinopril 10mg   │
│  daily and Type 2 Diabetes managed with      │
│  Metformin 500mg twice daily..."             │
│                                              │
│ ✅ REAL DATA!                                │
│ ✅ ACTUAL PATIENT INFORMATION!               │
│ ✅ SUCCESS!                                  │
└──────────────────────────────────────────────┘
```

---

## Summary

The fix adds **actual tool execution** to your system:

✅ Before: Tools were talked about but not used  
✅ Now: Tools are talked about AND used  
✅ Before: LLM had no real data  
✅ Now: LLM uses real database data  
✅ Before: Empty responses  
✅ Now: Detailed, data-driven responses  

**The missing piece was execution. It's now added.**

**Ready to test! Restart Django and try patient queries.**
