# System Architecture Diagrams – Before & After LLM Integration

## Current Architecture ✅ (Working Today)

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Browser)                        │
│                                                                   │
│   Django Template (dashboard.html)                               │
│   ├─ Quick Tools (tool selector + patient ID)                   │
│   ├─ Who Am I (show user/role)                                  │
│   ├─ My RBAC (show permissions matrix)                          │
│   ├─ Raw JSON-RPC (for testing)                                 │
│   └─ Audit Logs (show my access history)                        │
│                                                                   │
│   JavaScript (CSRF token, htmx setup)                           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    HTTP POST (with JWT)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   DJANGO BACKEND (port 8000)                    │
│                                                                   │
│   frontend/views.py                                              │
│   ├─ POST /mcp-proxy/  (JWT→MCP proxy) ✅ FIXED TODAY          │
│   ├─ GET /whoami       (user info)                              │
│   ├─ GET /rbac/*       (permission matrix)                      │
│   ├─ GET /audit-latest (user's audit log)                       │
│   └─ GET /mint-token   (JWT generation)                         │
│                                                                   │
│   Authentication:                                                │
│   └─ JWT from SimpleJWT (Authorization header)                  │
│                                                                   │
│   Session:                                                       │
│   └─ request.user populated from JWT token                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                JSON-RPC over HTTP (with JWT)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│            FASTAPI MCP SERVER (port 9000)                       │
│                                                                   │
│   mcp_server/main.py                                             │
│   ├─ JWT validation (same secret as Django)                     │
│   ├─ RBAC enforcement (is_allowed function)                     │
│   ├─ Tool implementation:                                        │
│   │  ├─ get_patient_overview                                    │
│   │  ├─ get_patient_admissions                                  │
│   │  ├─ get_patient_appointments                                │
│   │  ├─ get_patient_records                                     │
│   │  └─ get_my_shifts                                           │
│   ├─ PHI redaction (role-based)                                 │
│   └─ Audit logging                                               │
│                                                                   │
│   Database client (db_client.py)                                │
│   └─ Query with row-level filtering                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                        SQL Queries
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│           PostgreSQL Database (Azure)                           │
│                                                                   │
│   Schema:                                                        │
│   ├─ User (Django custom user model)                            │
│   ├─ Staff (doctor, nurse, admin profiles)                     │
│   ├─ Patient (non-PHI: name, DOB year, gender)                 │
│   ├─ PHIDemographics (sensitive: SSN, address, phone)          │
│   ├─ Admission (hospital stays)                                 │
│   ├─ Appointment (scheduled visits)                             │
│   ├─ MedicalRecord (diagnoses, treatments)                      │
│   ├─ Shift (staff scheduling)                                   │
│   └─ AuditLog (access tracking)                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Future Architecture ✨ (After LLM Integration)

```
┌──────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Browser)                               │
│                                                                        │
│   Option A: htmx + Django Template (Simple - Week 1)                │
│   ├─ Chat panel with message history                                 │
│   ├─ Input: "What are John's recent admissions?"                    │
│   ├─ htmx POST to /api/chat/message                                  │
│   └─ Display streaming responses in real-time                        │
│                                                                        │
│   Option B: React + Vite (Professional - Weeks 2-3)                 │
│   ├─ Chat.jsx (main component)                                       │
│   ├─ MessageList.jsx (message history)                               │
│   ├─ ChatInput.jsx (input area)                                      │
│   ├─ Sidebar.jsx (session list)                                      │
│   └─ Streaming message display with auto-scroll                      │
└──────────────────────────────────────────────────────────────────────┘
                          ↓ REST API (JSON)
                          ↓
┌──────────────────────────────────────────────────────────────────────┐
│                   DJANGO BACKEND (port 8000)                         │
│                                                                        │
│   frontend/models.py (NEW)                                            │
│   ├─ ChatSession (conversation container)                            │
│   └─ ChatMessage (message history)                                   │
│                                                                        │
│   frontend/llm_handler.py (NEW) ⭐                                    │
│   ├─ LLMConfig (API key, model, limits)                              │
│   ├─ SystemPromptManager (role-based prompts)                        │
│   └─ LLMAgentHandler (streaming, tools, auth)                        │
│                                                                        │
│   frontend/views.py (UPDATED)                                         │
│   ├─ POST /api/chat/session (create chat)                            │
│   ├─ GET /api/chat/sessions (list chats)                             │
│   ├─ POST /api/chat/message (send message + stream)                  │
│   ├─ GET /api/chat/history/<id> (load messages)                      │
│   │                                                                    │
│   │  Flow:                                                            │
│   │  1. User sends: "What are John's admissions?"                   │
│   │  2. Verify JWT + RBAC                                            │
│   │  3. Save user message to ChatMessage                             │
│   │  4. Call LLMAgentHandler.stream_response()                       │
│   │  5. Stream NDJSON to frontend                                    │
│   │  6. Each chunk saved to ChatMessage                              │
│   │                                                                    │
│   └─ Existing endpoints still work ✓                                 │
│      ├─ /mcp-proxy (now JWT-authed) ✓                                │
│      ├─ /whoami, /rbac, /audit-latest, /mint-token ✓                │
│                                                                        │
│   Authentication:                                                     │
│   └─ @api_view + @authentication_classes([JWTAuthentication])        │
│                                                                        │
│   Streaming:                                                          │
│   └─ StreamingHttpResponse(generator) for NDJSON                     │
└──────────────────────────────────────────────────────────────────────┘
         ↓                                    ↓
    LLM API Call                         MCP Server Call
         ↓                                    ↓
┌──────────────────────────────────┐ ┌──────────────────────────────────┐
│   LLM PROVIDER (External)        │ │  FASTAPI MCP SERVER (port 9000)  │
│                                  │ │                                  │
│   OpenAI: gpt-4-turbo           │ │  When LLM calls a tool:          │
│   Anthropic: Claude 3           │ │  ├─ Validate tool is allowed    │
│   Azure OpenAI: HIPAA BAA       │ │  ├─ Check user RBAC             │
│                                  │ │  ├─ Query database              │
│   Flow:                          │ │  ├─ Redact PHI by role          │
│   1. Django calls OpenAI API    │ │  ├─ Return JSON result          │
│   2. Sends role-based prompt    │ │  └─ Log audit event             │
│   3. System prompt narrows      │ │                                  │
│      available tools per role   │ │  Same as before, but now        │
│   4. LLM decides which tool     │ │  called dynamically by LLM      │
│      to call                    │ │                                  │
│   5. Django calls MCP tool      │ │  (Previously called manually)    │
│   6. Returns result to LLM      │ │                                  │
│   7. LLM generates response     │ └──────────────────────────────────┘
│   8. Streamed to frontend       │
└──────────────────────────────────┘
         ↓
┌──────────────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database (Azure)                       │
│                                                                        │
│   Existing tables (unchanged):                                        │
│   ├─ User, Staff, Patient, PHIDemographics                           │
│   ├─ Admission, Appointment, MedicalRecord, Shift                    │
│   └─ AuditLog                                                         │
│                                                                        │
│   New tables:                                                         │
│   ├─ ChatSession (one per conversation)                              │
│   ├─ ChatMessage (one per message)                                   │
│   └─ TokenUsageLog (optional: cost tracking)                         │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: User Asking LLM a Question

```
User (Browser):
  Inputs: "What are John's recent admissions?"
  Clicks: "Send"
         ↓
         │ HTTP POST
         │ /api/chat/message
         │ {"session_id": "uuid-xxx", "message": "What are..."}
         ↓
Django Backend:
  1. Verify JWT token
  2. Extract user from token
  3. Get user's role (Doctor, Nurse, Admin, etc)
  4. Create ChatMessage(role="user", content="What are...")
  5. Initialize LLMAgentHandler(user, ip_address)
     - Loads role-specific system prompt
     - Determines available tools based on role
  6. Call llm_handler.stream_response("What are...")
         ↓
LLMAgentHandler.stream_response():
  1. Build messages:
     [
       {"role": "system", "content": "You are a Doctor AI assistant..."},
       {"role": "user", "content": "What are John's recent admissions?"}
     ]
  2. Determine available tools for Doctor role:
     - get_patient_overview ✓
     - get_patient_admissions ✓
     - get_patient_appointments ✓
     - get_patient_records ✓
     - (NOT: billing tools, not available to Doctors)
  3. Call OpenAI with streaming:
     openai.ChatCompletion.create(
       model="gpt-4-turbo-preview",
       messages=messages,
       tools=available_tools,
       stream=True,
       ...
     )
  4. For each chunk:
     - If text: yield {"type": "message", "content": "..."}
     - If tool call: yield {"type": "tool_call", "content": {...}}
         ↓
OpenAI API returns:
  Chunk 1: {"delta": {"content": "Let me look up"}}
  Chunk 2: {"delta": {"content": " patient John"}}
  Chunk 3: {"delta": {"tool_calls": [{"function": {"name": "get_patient_admissions", "arguments": {"patient_id": "PAT-001"}}}]}}
         ↓
Django streams back to browser (NDJSON):
  {"type": "message", "content": "Let me look up"}
  {"type": "message", "content": " patient John"}
  {"type": "tool_call", "content": {"function": {...}}}
  
  (Also saves each to ChatMessage database)
         ↓
Frontend (Browser) streams in:
  1. Display "Let me look up"
  2. Display "patient John"
  3. Show Tool Call section: "get_patient_admissions(PAT-001)"
         ↓
Django (in background) executes tool:
  1. Receives tool_call: {"function": {"name": "get_patient_admissions", ...}}
  2. Validates: Is get_patient_admissions allowed for Doctor role? ✓
  3. Calls MCP: POST http://127.0.0.1:9000/mcp/
     {
       "jsonrpc": "2.0",
       "id": 1,
       "method": "tools.call",
       "params": {"name": "get_patient_admissions", "arguments": {"patient_id": "PAT-001"}}
     }
     Header: Authorization: Bearer {same JWT}
         ↓
MCP Server validates:
  1. Verify JWT signature (same JWT_SECRET)
  2. Decode JWT → extract user_id + role
  3. Check RBAC: Can this Doctor see patient PAT-001's admissions?
     - is_allowed("MedicalRecord", "view", "Doctor", user_id, row_context)
     - If assigned: ✓ Allow
     - If not assigned: ✗ Deny → return 403 + log ACCESS_DENIED
  4. Query database:
     Admission.objects.filter(patient_id="PAT-001")
  5. Redact PHI for Doctor role:
     - Remove: SSN, full address, insurance details
     - Show: admission_date, discharge_date, reason
  6. Return JSON result
  7. Log: AuditLog(action="MCP_TOOL_CALL", tool_name="get_patient_admissions", is_phi=True)
         ↓
Django receives result:
  {
    "jsonrpc": "2.0",
    "id": 1,
    "result": [
      {
        "admission_id": "ADM-001",
        "admission_date": "2024-01-15",
        "discharge_date": "2024-01-20",
        "reason": "Routine checkup",
        "redacted_phi": "[REDACTED]"
      }
    ]
  }
         ↓
Django resumes LLM streaming:
  1. Returns tool result to OpenAI
  2. OpenAI generates final response:
     "John was admitted on January 15, 2024..."
  3. Streams to frontend:
     {"type": "message", "content": "John was admitted on January 15, 2024..."}
         ↓
Frontend receives and displays:
  Complete conversation:
  ├─ User: "What are John's recent admissions?"
  ├─ Assistant: "Let me look up patient John"
  ├─ Tool Call: get_patient_admissions(PAT-001)
  └─ Assistant: "John was admitted on January 15, 2024..."
         ↓
Audit Trail:
  - LLM_CALL (user, datetime, ip)
  - LLM_TOOL_CALL (user, get_patient_admissions, patient_id)
  - MCP_TOOL_CALL (same from MCP side)
  All marked as is_phi_access=True for compliance
```

---

## RBAC Enforcement with LLM

```
┌─ DOCTOR LOGIN ─────────────────────────────────────────────┐
│                                                             │
│ System Prompt:                                              │
│ "You are a Doctor AI assistant. You can view patient       │
│  information for your assigned patients. You CANNOT        │
│  view full PHI (SSN, full addresses). This data is        │
│  automatically redacted."                                  │
│                                                             │
│ Available Tools:                                            │
│ ✓ get_patient_overview                                     │
│ ✓ get_patient_admissions                                   │
│ ✓ get_patient_appointments                                 │
│ ✓ get_patient_records                                      │
│ ✓ get_my_shifts                                            │
│ ✗ (Billing tools not in the list)                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─ BILLING STAFF LOGIN ──────────────────────────────────────┐
│                                                             │
│ System Prompt:                                              │
│ "You are a Billing AI assistant. You can access patient   │
│  insurance information only. You CANNOT view medical       │
│  records or clinical data."                               │
│                                                             │
│ Available Tools:                                            │
│ ✓ get_patient_overview (insurance fields only)             │
│ ✗ (No medical tools available)                             │
│ ✗ get_patient_admissions → NOT IN LIST                     │
│ ✗ get_patient_records → NOT IN LIST                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─ AUDITOR LOGIN ───────────────────────────────────────────┐
│                                                             │
│ System Prompt:                                              │
│ "You are a Compliance AI assistant. You can view all      │
│  data including audit logs for compliance purposes."      │
│                                                             │
│ Available Tools:                                            │
│ ✓ get_patient_overview (FULL including SSN)                │
│ ✓ get_patient_admissions (ALL records)                     │
│ ✓ get_patient_appointments (ALL records)                   │
│ ✓ get_patient_records (FULL including diagnoses)           │
│ ✓ get_my_shifts (access logs)                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─ RECEPTION LOGIN ─────────────────────────────────────────┐
│                                                             │
│ System Prompt:                                              │
│ "You are a Reception AI assistant. You can help with      │
│  appointment scheduling and basic patient information."   │
│                                                             │
│ Available Tools:                                            │
│ ✓ get_patient_overview (name, DOB year only)               │
│ ✗ get_patient_admissions → NOT IN LIST                     │
│ ✗ get_patient_records → NOT IN LIST                        │
│ ✗ get_my_shifts → NOT IN LIST                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

```
PHASE 1: Backend (Days 1-2) ⭐ CRITICAL
┌──────────────────────────────────────┐
│ ✓ Create llm_handler.py              │
│ ✓ Add ChatSession & ChatMessage      │
│ ✓ Add 4 API endpoints                │
│ ✓ Test with cURL streaming           │
│ ✓ Verify RBAC in LLM prompts         │
│ ✓ Verify audit logging works         │
│                                      │
│ Success: Streaming works via curl    │
└──────────────────────────────────────┘
        ↓
PHASE 2: Frontend (Days 3-5) ⚠️ OPTIONAL
┌──────────────────────────────────────┐
│ OPTION A: Simple (htmx - 4 hours)    │
│ ├─ Add chat panel to dashboard       │
│ ├─ Use htmx POST                     │
│ ├─ Display messages in div           │
│                                      │
│ OR                                   │
│                                      │
│ OPTION B: Professional (React - 16h) │
│ ├─ Build React component             │
│ ├─ Create message list               │
│ ├─ Add chat history sidebar          │
│ ├─ Polish with Tailwind CSS          │
│                                      │
│ Success: Chat works in browser       │
└──────────────────────────────────────┘
        ↓
PHASE 3: Polish (Week 2) 🚀 NICE-TO-HAVE
┌──────────────────────────────────────┐
│ ✓ Rate limiting                      │
│ ✓ Token usage tracking               │
│ ✓ Cost alerts                        │
│ ✓ Error recovery                     │
│ ✓ Load testing                       │
│ ✓ Security audit                     │
│                                      │
│ Success: Production-ready            │
└──────────────────────────────────────┘
```

---

## Tech Stack Comparison

```
┌─────────────────────────────────────────────────────────────┐
│ CURRENT STACK (Working Today ✓)                             │
├─────────────────────────────────────────────────────────────┤
│ Frontend:   Django Templates + htmx + vanilla JS            │
│ Backend:    Django REST Framework + SimpleJWT               │
│ API Layer:  FastAPI (MCP server on port 9000)               │
│ Database:   PostgreSQL (Azure)                              │
│ Auth:       JWT (Bearer token)                              │
│ Transport:  HTTP/HTTPS                                      │
│ Logging:    Django ORM (AuditLog model)                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ AFTER LLM INTEGRATION (Options)                             │
├─────────────────────────────────────────────────────────────┤
│ OPTION A: Keep Current (htmx)                               │
│ ├─ Frontend:   Django Templates + htmx + JS                 │
│ ├─ Backend:    Add llm_handler.py module                    │
│ ├─ LLM:        OpenAI API (streaming)                       │
│ ├─ Protocol:   NDJSON (newline-delimited JSON)              │
│ ├─ Storage:    ChatSession + ChatMessage models             │
│ └─ Complexity: Low (best for MVP)                           │
│                                                             │
│ OPTION B: Modernize (React + Vite)                         │
│ ├─ Frontend:   React 18 + Vite + Tailwind CSS               │
│ ├─ Backend:    Same as above                                │
│ ├─ API:        REST endpoints return NDJSON                 │
│ ├─ Storage:    Same database models                         │
│ └─ Complexity: Higher (better for long-term)               │
│                                                             │
│ OPTION C: Advanced (WebSocket)                             │
│ ├─ Frontend:   React + WebSocket client                     │
│ ├─ Backend:    Django Channels for WebSocket               │
│ ├─ Protocol:   WebSocket (persistent connection)            │
│ ├─ Storage:    Same database models                         │
│ └─ Complexity: Highest (better for real-time)              │
└─────────────────────────────────────────────────────────────┘
```

---

## Security Layers (Defense in Depth)

```
Layer 1: Authentication (Entry)
├─ JWT token required for all API calls
├─ Token signed with JWT_SECRET (same for Django + MCP)
└─ Invalid/missing token = 401 Unauthorized

Layer 2: Authorization (RBAC)
├─ User role extracted from JWT
├─ System prompt tailored to role
├─ Tool availability filtered by role
├─ MCP enforces RBAC again for each tool call
└─ Role mismatch = 403 Forbidden + audit log

Layer 3: Data Filtering (Row-level)
├─ Doctor can only see assigned patients
├─ Billing can only see insurance fields
├─ MCP applies row filters before returning data
└─ Unauthorized access = 403 + ACCESS_DENIED audit event

Layer 4: PHI Redaction (Field-level)
├─ Sensitive fields removed based on role
├─ Doctor sees medical data, not SSN
├─ Billing sees insurance, not address
├─ Redaction happens in MCP before returning JSON
└─ UI marks redacted data as [REDACTED]

Layer 5: Audit Logging (Compliance)
├─ Every action logged with user, timestamp, IP
├─ PHI access flagged for review
├─ Tool calls recorded with arguments
├─ Access denials logged separately
└─ Compliance team can query audit trail

Layer 6: Monitoring (Detection)
├─ Alert on repeated 403 errors (brute force?)
├─ Alert on unusual tool usage patterns
├─ Alert on cost thresholds exceeded
├─ Alert on rate limiting triggered
└─ Daily compliance report generated
```

---

This architecture ensures:
✅ **Security**: Multiple layers of protection
✅ **Compliance**: Full audit trail for HIPAA
✅ **Scalability**: Stateless API design
✅ **Maintainability**: Clear separation of concerns
✅ **User Experience**: Real-time streaming responses
