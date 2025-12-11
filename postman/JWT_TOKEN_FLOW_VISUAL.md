# JWT Token Flow - Visual Diagram

## The Problem (401 Unauthorized)

```
Browser Request with JWT                     MCP Server expects JWT
         │                                             │
         ▼                                             ▼
    ┌─────────────────────────────────────────────────────┐
    │  Authorization: Bearer <django-jwt>                │
    │  Content: {"message": "Get patient records"}       │
    └─────────────────┬───────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────────┐
         │   Django View Handler      │
         │  (has user info)           │
         │                            │
         │  ❌ Tries to extract token │
         │     from Django request    │
         │  ❌ No token found         │
         │  ❌ Sends empty header     │
         └────────────┬───────────────┘
                      │
                      ▼
    POST /mcp/ HTTP/1.1
    Content-Type: application/json
    ❌ NO Authorization Header
    
    {"jsonrpc":"2.0","method":"get_medical_records","params":{"arguments":{"patient_id":"NUGWI"}}}
                      │
                      ▼
         ┌────────────────────────────┐
         │   MCP Server               │
         │                            │
         │  Checks Authorization:     │
         │  - Not found ❌            │
         │  - Raises 401              │
         │  - Returns error           │
         └────────────┬───────────────┘
                      │
                      ▼
    HTTP/1.1 401 Unauthorized
    {"error": "Missing Authorization token"}
    
    ❌ NO DATA RETURNED
    ❌ TOOL DOESN'T EXECUTE
    ❌ LLM GETS EMPTY RESPONSE
```

---

## The Solution (Generate JWT Token)

```
Browser Request              (User already authenticated)
         │
         ▼
    ┌─────────────────────────────────────────────────────┐
    │  POST /api/chat/message/                           │
    │  Content: {"message": "Get patient records"}       │
    └─────────────────┬───────────────────────────────────┘
                      │
                      ▼
         ┌────────────────────────────────────────┐
         │   Django View Handler                  │
         │   - Has authenticated user ✅          │
         │   - user.id = 1                       │
         │   - user.role = "Doctor"              │
         └────────────┬───────────────────────────┘
                      │
                      ▼
         ┌────────────────────────────────────────────┐
         │   LLMAgentHandler._execute_tool()         │
         │                                           │
         │   ✅ Read JWT_SECRET from .env            │
         │   ✅ Create JWT payload:                  │
         │      {"user_id": "1",                     │
         │       "role": "Doctor",                   │
         │       "username": "yenji100"}            │
         │   ✅ Sign with HS256 + JWT_SECRET        │
         │   ✅ Get token:                          │
         │      eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... │
         │   ✅ Add Authorization header           │
         └────────────┬───────────────────────────┘
                      │
                      ▼
    POST /mcp/ HTTP/1.1
    Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    Content-Type: application/json
    
    {"jsonrpc":"2.0","method":"get_medical_records","params":{"arguments":{"patient_id":"NUGWI"}}}
                      │
                      ▼
         ┌────────────────────────────────────────┐
         │   MCP Server                           │
         │                                        │
         │   ✅ Extract token from header        │
         │   ✅ Decode using JWT_SECRET          │
         │   ✅ Verify signature matches         │
         │   ✅ Get user_id="1", role="Doctor"  │
         │   ✅ Check RBAC: Doctor can get      │
         │      patient records ✅               │
         │   ✅ Query database                   │
         │   ✅ Redact PHI if needed            │
         └────────────┬───────────────────────────┘
                      │
                      ▼
    HTTP/1.1 200 OK
    {"result": {"data": [
        {"id": "PAT-001", "name": "John Doe", 
         "diagnoses": ["Type 2 Diabetes", "Hypertension"]},
        {"id": "PAT-002", "name": "Jane Smith", 
         "diagnoses": ["COPD"]}
    ]}}
    
    ✅ ACTUAL DATA RETURNED
    ✅ TOOL EXECUTED SUCCESSFULLY
    ✅ LLM RECEIVES PATIENT INFORMATION
```

---

## Token Creation Process (Detail)

```
┌──────────────────────────────────────────────────────────────┐
│  STEP 1: Read Configuration                                  │
├──────────────────────────────────────────────────────────────┤
│  jwt_secret = os.getenv("JWT_SECRET", "")                   │
│  jwt_alg = os.getenv("JWT_ALG", "HS256")                    │
│                                                               │
│  Result:                                                     │
│  - jwt_secret = "django-insecure-secret-key"               │
│  - jwt_alg = "HS256"                                        │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 2: Validate Configuration                              │
├──────────────────────────────────────────────────────────────┤
│  if not jwt_secret:                                          │
│      return {"success": False, "error": "..."}              │
│                                                               │
│  Result:                                                     │
│  - jwt_secret exists ✅                                      │
│  - Continue to token creation ✅                             │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 3: Create Token Payload                                │
├──────────────────────────────────────────────────────────────┤
│  payload = {                                                 │
│      "user_id": str(self.user.id),        # "1"             │
│      "role": self.role,                   # "Doctor"        │
│      "username": self.user.username,      # "yenji100"      │
│  }                                                            │
│                                                               │
│  Result:                                                     │
│  payload = {                                                 │
│      "user_id": "1",                                         │
│      "role": "Doctor",                                       │
│      "username": "yenji100"                                  │
│  }                                                            │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 4: Sign Token                                          │
├──────────────────────────────────────────────────────────────┤
│  mcp_token = jwt.encode(payload, jwt_secret, algorithm=jwt_alg) │
│                                                               │
│  Behind the scenes:                                          │
│  1. Encode payload as JSON: {"user_id":"1",...}            │
│  2. Base64-encode: eyJwYXlsb2FkIn0=                         │
│  3. Create signature using HMAC-SHA256                       │
│     - Input: header + payload                               │
│     - Key: jwt_secret ("django-insecure-secret-key")        │
│     - Output: HMAC hash                                      │
│  4. Combine: header.payload.signature                        │
│                                                               │
│  Result:                                                     │
│  mcp_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." (256 chars) │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 5: Add Token to Request Headers                        │
├──────────────────────────────────────────────────────────────┤
│  headers = {                                                 │
│      "Content-Type": "application/json",                    │
│      "Authorization": f"Bearer {mcp_token}"                 │
│  }                                                            │
│                                                               │
│  Result:                                                     │
│  headers = {                                                 │
│      "Content-Type": "application/json",                    │
│      "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." │
│  }                                                            │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 6: Send Request to MCP                                 │
├──────────────────────────────────────────────────────────────┤
│  response = requests.post(                                   │
│      mcp_url,                                                │
│      json=payload,                                           │
│      timeout=30,                                             │
│      headers=headers  # ✅ Includes Authorization           │
│  )                                                            │
│                                                               │
│  HTTP Request sent:                                          │
│  POST http://127.0.0.1:5000/mcp/ HTTP/1.1                  │
│  Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  │
│  Content-Type: application/json                             │
│                                                               │
│  {"jsonrpc":"2.0","method":"get_medical_records",...}      │
└──────────────────────────────────────────────────────────────┘
```

---

## Token Validation on MCP Server (Mirror Process)

```
┌──────────────────────────────────────────────────────────────┐
│  STEP 1: Receive Authorization Header                        │
├──────────────────────────────────────────────────────────────┤
│  auth = request.headers.get("Authorization", "")            │
│  # auth = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  │
│                                                               │
│  if not auth.startswith("Bearer "):                          │
│      raise 401 "Missing Bearer token"                       │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 2: Extract Token                                       │
├──────────────────────────────────────────────────────────────┤
│  token = auth.split(" ", 1)[1]                              │
│  # token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."        │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 3: Decode Token                                        │
├──────────────────────────────────────────────────────────────┤
│  JWT_SECRET = os.getenv("JWT_SECRET")  # "django-insecure-secret-key" │
│  JWT_ALG = os.getenv("JWT_ALG", "HS256")                    │
│                                                               │
│  claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG]) │
│                                                               │
│  Behind the scenes:                                          │
│  1. Split token: header.payload.signature                   │
│  2. Extract signature from token                             │
│  3. Recreate signature using:                                │
│     - header + payload (same data)                           │
│     - JWT_SECRET ("django-insecure-secret-key")             │
│     - HMAC-SHA256                                            │
│  4. Compare: token signature == recreated signature          │
│     - If match ✅: Token is valid                            │
│     - If mismatch ❌: Token is forged/tampered               │
│  5. If valid, decode payload to get claims                   │
│                                                               │
│  ❌ If JWT_SECRET doesn't match: Signature fails validation  │
│  ❌ If token expired: ExpiredSignatureError                  │
│  ❌ If token malformed: InvalidTokenError                    │
│                                                               │
│  Result (if valid):                                          │
│  claims = {                                                  │
│      "user_id": "1",                                         │
│      "role": "Doctor",                                       │
│      "username": "yenji100"                                  │
│  }                                                            │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 4: Extract Identity                                    │
├──────────────────────────────────────────────────────────────┤
│  user_id = claims.get("user_id")  # "1"                     │
│  role = claims.get("role")        # "Doctor"                │
│                                                               │
│  if not user_id:                                             │
│      raise 401 "Token missing user_id"                      │
│                                                               │
│  Result:                                                     │
│  identity = Identity(user_id="1", role="Doctor", ...)      │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 5: Check RBAC                                          │
├──────────────────────────────────────────────────────────────┤
│  method = "get_medical_records"                              │
│  role = "Doctor"                                             │
│                                                               │
│  Can Doctor call get_medical_records?                        │
│  - Check RBAC matrix                                         │
│  - Result: YES ✅                                             │
│  - Proceed to execution                                      │
│                                                               │
│  Result:                                                     │
│  RBAC check passed ✅                                         │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 6: Execute Tool                                        │
├──────────────────────────────────────────────────────────────┤
│  patient_id = "NUGWI"                                        │
│                                                               │
│  result = get_medical_records_for_patient(patient_id)       │
│  result = [                                                  │
│      {"id": 1, "date": "2025-11-10", "note": "Follow-up"},  │
│      {"id": 2, "date": "2025-11-05", "note": "Initial"}     │
│  ]                                                            │
│                                                               │
│  Result:                                                     │
│  ✅ Patient data retrieved                                   │
└──────────────────────────────────────────────────────────────┘
                          ↓
┌──────────────────────────────────────────────────────────────┐
│  STEP 7: Return Response                                     │
├──────────────────────────────────────────────────────────────┤
│  return {                                                    │
│      "jsonrpc": "2.0",                                       │
│      "id": 1,                                                │
│      "result": {                                             │
│          "data": [...]  # ✅ ACTUAL PATIENT DATA            │
│      }                                                        │
│  }                                                            │
│                                                               │
│  HTTP Response: 200 OK ✅                                     │
│  Body: {"result": {"data": [...]}}                          │
└──────────────────────────────────────────────────────────────┘
```

---

## Why This Works (Cryptography)

```
HMAC-SHA256 Signing
═══════════════════

Create Token (Django Handler):
┌─────────────────────────────────────────────────┐
│ Payload:  {"user_id": "1", "role": "Doctor"}   │
│ Secret:   "django-insecure-secret-key"         │
│ Algorithm: HS256 (HMAC-SHA256)                  │
│                                                  │
│ Process:                                         │
│ 1. Input: payload + secret                      │
│ 2. HMAC function: HMAC(payload, secret)         │
│ 3. Output: signature (256-bit hash)             │
│ 4. Token: base64(header + payload + signature)  │
│                                                  │
│ Result: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... │
└─────────────────────────────────────────────────┘

Validate Token (MCP Server):
┌─────────────────────────────────────────────────┐
│ Token:    eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... │
│ Secret:   "django-insecure-secret-key"  (SAME!) │
│ Algorithm: HS256 (HMAC-SHA256)                  │
│                                                  │
│ Process:                                         │
│ 1. Extract: header, payload, signature          │
│ 2. Recreate signature:                          │
│    signature_new = HMAC(header+payload, secret) │
│ 3. Compare:                                      │
│    signature_from_token == signature_new?       │
│                                                  │
│ If YES ✅:                                       │
│    - Token is authentic (not tampered)          │
│    - Payload is trustworthy                     │
│    - Proceed with execution                     │
│                                                  │
│ If NO ❌:                                        │
│    - Token is forged or tampered                │
│    - Reject with 401 Unauthorized               │
└─────────────────────────────────────────────────┘

Why Both Must Use Same Secret:
═════════════════════════════════════════════════

If secrets match (✅ CORRECT):
┌─────────────────────────────────────┐
│ Create:  HMAC(data, "my-secret")   │
│ Result:  hash123                    │
├─────────────────────────────────────┤
│ Verify:  HMAC(data, "my-secret")   │
│ Result:  hash123                    │
├─────────────────────────────────────┤
│ hash123 == hash123? YES ✅           │
│ Token is valid                      │
└─────────────────────────────────────┘

If secrets don't match (❌ WRONG):
┌─────────────────────────────────────┐
│ Create:  HMAC(data, "secret-A")    │
│ Result:  hashA                      │
├─────────────────────────────────────┤
│ Verify:  HMAC(data, "secret-B")    │
│ Result:  hashB                      │
├─────────────────────────────────────┤
│ hashA == hashB? NO ❌                │
│ Token rejected: 401 Unauthorized    │
└─────────────────────────────────────┘
```

---

## Configuration Diagram

```
System Setup:
═════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────┐
│  .env (Environment Configuration)                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  # CRITICAL: Must be identical in Django and MCP           │
│  JWT_SECRET=django-insecure-my-secret-key                  │
│  JWT_ALG=HS256                                             │
│                                                              │
│  # Django settings                                          │
│  LLM_API_KEY=sk-...                                        │
│  LLM_PROVIDER=openai                                       │
│                                                              │
│  # MCP server URL                                           │
│  MCP_SERVER_URL=http://127.0.0.1:5000/mcp/                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
         │
         ├──────────────────────────────┬──────────────────────────────┐
         │                              │                              │
         ▼                              ▼                              ▼
    ┌──────────────┐           ┌──────────────┐           ┌──────────────┐
    │   Django     │           │  MCP Server  │           │ OpenAI LLM   │
    │   Handler    │           │              │           │              │
    │              │           │              │           │              │
    │ Reads:       │           │ Reads:       │           │ Reads:       │
    │ JWT_SECRET ✅│           │ JWT_SECRET ✅│           │ LLM_API_KEY  │
    │ JWT_ALG      │           │ JWT_ALG      │           │              │
    │              │           │              │           │              │
    │ Creates JWT  │           │ Validates    │           │ Generates    │
    │ with secret ✅│───POST───▶│ JWT with     │           │ response     │
    │              │ + token   │ same secret ✅           │              │
    │              │           │              │           │              │
    │              │           │ Executes tool│           │              │
    │              │           │ Returns data │────────────▶             │
    │              │◀──────────│              │           │              │
    │ Receives data│ response  │              │           │              │
    │ Sends to LLM │           │              │           │              │
    │              │           │              │           │              │
    └──────────────┘           └──────────────┘           └──────────────┘
```

---

## Summary

✅ **Django Handler**:
- Reads JWT_SECRET and JWT_ALG from .env
- Creates JWT token with user_id and role claims
- Signs token using HMAC-SHA256
- Includes token in Authorization header
- Sends request to MCP server

✅ **MCP Server**:
- Receives Authorization header
- Extracts JWT token
- Decodes token using SAME JWT_SECRET
- Validates signature (ensures token not tampered)
- Extracts claims (user_id, role)
- Executes tool with user context
- Returns data

✅ **Security**:
- Only MCP server can verify tokens (has JWT_SECRET)
- Tokens can't be forged without secret
- Signature ensures token integrity
- Claims provide user context for RBAC

✅ **Result**:
- ✅ No more 401 errors
- ✅ Tools execute successfully
- ✅ Patient data returned
- ✅ LLM has context for responses
