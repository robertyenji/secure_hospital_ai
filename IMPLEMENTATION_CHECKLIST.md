# Frontend Implementation Checklist – Priority Order

## ✅ CRITICAL (Must Do Before LLM Integration)

### 1. Backend API Endpoints (Days 1-2)
- [ ] Create `frontend/llm_handler.py` with:
  - [ ] `LLMAgentHandler` class
  - [ ] `SystemPromptManager` with role-based prompts
  - [ ] `stream_response()` method for streaming
  - [ ] `_get_available_tools()` RBAC filtering
  - [ ] `_log_audit()` for compliance

- [ ] Create `frontend/chat_handler.py` with:
  - [ ] `ChatSession` model
  - [ ] `ChatMessage` model
  - [ ] `ChatContextManager` helper class

- [ ] Update `frontend/views.py` with new endpoints:
  - [ ] `POST /api/chat/message` (streaming)
  - [ ] `POST /api/chat/session` (new chat)
  - [ ] `GET /api/chat/sessions` (list all)
  - [ ] `GET /api/chat/history/<session_id>` (load chat)

- [ ] Run migrations:
  ```bash
  python manage.py makemigrations frontend
  python manage.py migrate
  ```

### 2. Environment Configuration (Day 1)
- [ ] Add to `.env`:
  ```
  LLM_PROVIDER=openai
  LLM_MODEL=gpt-4-turbo-preview
  LLM_API_KEY=sk-...
  LLM_TEMPERATURE=0.7
  LLM_MAX_TOKENS=2000
  ```

- [ ] Update `settings.py` with LLM config
- [ ] Test LLM API key works:
  ```bash
  python -c "import openai; print(openai.Model.list())"
  ```

### 3. Test Backend Endpoints (Days 2-3)
- [ ] Test session creation:
  ```bash
  curl -X POST http://localhost:8000/api/chat/session \
    -H "Authorization: Bearer <jwt>" \
    -H "Content-Type: application/json" \
    -d '{"title": "Test Chat"}'
  ```

- [ ] Test message streaming:
  ```bash
  curl -X POST http://localhost:8000/api/chat/message \
    -H "Authorization: Bearer <jwt>" \
    -H "Content-Type: application/json" \
    -d '{"session_id": "uuid", "message": "List patient PAT-001"}' \
    --no-buffer
  ```

- [ ] Verify audit logs created:
  ```bash
  python manage.py shell
  >>> from audit.models import AuditLog
  >>> AuditLog.objects.filter(action="LLM_CALL").count()
  ```

---

## ⚠️ IMPORTANT (Do Before UI Goes Live)

### 4. Rate Limiting (Day 3)
- [ ] Install `django-ratelimit`:
  ```bash
  pip install django-ratelimit
  ```

- [ ] Add to `chat_message` view:
  ```python
  @ratelimit(key='user', rate='100/h', method='POST')
  @api_view(['POST'])
  def chat_message(request):
      # ...
  ```

### 5. Error Handling & Logging (Day 3)
- [ ] Create `frontend/exceptions.py`:
  ```python
  class ToolNotAllowed(Exception):
      pass
  
  class LLMError(Exception):
      pass
  ```

- [ ] Set up logging in `llm_handler.py`:
  ```python
  import logging
  logger = logging.getLogger(__name__)
  ```

- [ ] Add try/catch blocks around all LLM calls

### 6. Token Usage Tracking (Day 4)
- [ ] Create `TokenUsageLog` model:
  ```python
  class TokenUsageLog(models.Model):
      session = ForeignKey(ChatSession)
      prompt_tokens = IntegerField()
      completion_tokens = IntegerField()
      estimated_cost = DecimalField()
  ```

- [ ] Store token counts after each LLM call

### 7. Prompt Injection Prevention (Day 4)
- [ ] Create input validation function:
  ```python
  def sanitize_prompt(text):
      # Remove SQL patterns
      # Remove prompt injection attempts
      # Limit to 5000 chars
      return text[:5000]
  ```

- [ ] Validate all user inputs before sending to LLM

---

## 🎨 FRONTEND (Can Parallelize with Backend - Days 2-5)

### 8. Choose Frontend Stack
- [ ] **Recommended: React + Vite** (fastest setup)
  OR
- [ ] **Vue.js + Vite** (simpler learning curve)
  OR
- [ ] **htmx + Django templates** (minimal JS, keep current setup)

**My Recommendation**: Stick with **htmx + Django templates** for MVP (simplicity), then migrate to React once stable.

### 9. Update Dashboard (Days 2-3)
If going htmx route:

- [ ] Update `dashboard.html`:
  ```html
  <!-- Chat history panel -->
  <div class="chat-history">
    <div hx-get="{% url 'frontend:chat_sessions' %}"
         hx-trigger="load"
         hx-swap="innerHTML"></div>
  </div>

  <!-- Chat messages area -->
  <div id="chat-messages" class="chat-area">
    <!-- Messages load here -->
  </div>

  <!-- Chat input -->
  <form hx-post="{% url 'frontend:chat_message' %}"
        hx-target="#chat-messages"
        hx-swap="beforeend"
        hx-on::after-swap="scrollToBottom()">
    <input name="message" placeholder="Ask something...">
    <button type="submit">Send</button>
  </form>
  ```

- [ ] Create `static/chat.js`:
  ```javascript
  // Handle streaming responses
  // Auto-scroll to bottom
  // Pretty-print JSON tool calls
  ```

### 10. Or: Build React Component (Days 2-5)
If going React route:

- [ ] Set up React project
- [ ] Create `Chat.jsx` main component
- [ ] Create `MessageList.jsx` component
- [ ] Create `ChatInput.jsx` component
- [ ] Create `Sidebar.jsx` component
- [ ] Set up API hooks with axios
- [ ] Add Tailwind for styling

---

## 🔒 SECURITY & COMPLIANCE (Parallel - Days 1-5)

### 11. Security Hardening
- [ ] Validate all tool calls before executing
- [ ] Never expose internal errors to LLM
- [ ] Rate limit LLM calls per user
- [ ] Log all PHI access via LLM
- [ ] Add CSRF protection (already done ✓)
- [ ] Validate JWT on every request (already done ✓)

### 12. Audit Trail
- [ ] Log action, tool_name, params, result, timestamp for each LLM call
- [ ] Mark PHI access clearly in audit logs
- [ ] Create audit dashboard to review LLM activity
- [ ] Alert on suspicious patterns (e.g., multiple denials)

### 13. Testing
- [ ] Unit tests for `LLMAgentHandler`
- [ ] Unit tests for `ChatContextManager`
- [ ] Integration tests for streaming endpoints
- [ ] RBAC tests (doctor can't see billing tools)
- [ ] PHI redaction tests

---

## 📊 MONITORING & OPS (Week 2)

### 14. Monitoring Dashboard
- [ ] Track token usage per user/day
- [ ] Monitor LLM API latency
- [ ] Track error rates
- [ ] Set alerts for cost thresholds

### 15. Database Optimization
- [ ] Add indexes on `ChatSession.user` and `ChatMessage.session`
- [ ] Archive old chat sessions periodically
- [ ] Monitor database size growth

---

## 🚀 RECOMMENDED IMPLEMENTATION ORDER

**Week 1: Backend Foundation**
1. Create `llm_handler.py` (Day 1)
2. Create `chat_handler.py` (Day 1)
3. Add API endpoints (Day 2)
4. Test with curl/Postman (Days 2-3)
5. Add error handling (Day 3)
6. Add rate limiting (Day 3)
7. Token usage tracking (Day 4)

**Week 2: Frontend**
8. Update dashboard OR build React (Days 2-5)
9. Connect to new API endpoints (Days 4-5)
10. Streaming response handling (Day 5)
11. Chat history UI (Week 2)

**Week 3: Polish & Deploy**
12. Security hardening (Days 1-2)
13. Testing (Days 1-3)
14. Monitoring setup (Days 3-5)
15. Deploy to production (Week 4)

---

## 📝 QUICK REFERENCE: File Changes Summary

### Files to Create:
```
frontend/llm_handler.py          (NEW - LLM agent handler)
frontend/chat_handler.py         (NEW - chat models & manager)
frontend/exceptions.py           (NEW - custom exceptions)
FRONTEND_IMPLEMENTATION_GUIDE.md  (NEW - detailed guide)
```

### Files to Modify:
```
frontend/views.py                (ADD 4 new endpoints)
frontend/urls.py                 (ADD 4 new routes)
frontend/models.py               (ADD if needed)
frontend/templates/dashboard.html (UPDATE chat UI)
secure_hospital_ai/settings.py   (ADD LLM config)
.env                             (ADD LLM credentials)
```

### No Changes Needed:
```
✓ frontend/mcp_proxy - Already JWT-authenticated (fixed earlier)
✓ mcp_server/main.py - Already working
✓ audit/models.py - Already tracking events
✓ Django authentication - SimpleJWT working
```

---

## 🧪 Testing Checklist

```bash
# 1. Backend Setup
python manage.py makemigrations frontend
python manage.py migrate

# 2. Test LLM Connection
python -c "from frontend.llm_handler import LLMAgentHandler; print('OK')"

# 3. Test Chat Creation
curl -X POST http://localhost:8000/api/chat/session \
  -H "Authorization: Bearer <jwt>"

# 4. Test Chat Message (with streaming)
curl -X POST http://localhost:8000/api/chat/message \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "uuid", "message": "test"}' \
  --no-buffer

# 5. Test RBAC
# Login as Doctor, verify can't access Billing tools
# Login as Auditor, verify can access all tools

# 6. Test Audit Logging
python manage.py shell
>>> from audit.models import AuditLog
>>> AuditLog.objects.filter(action__contains="LLM").count()

# 7. Load Test (simulate 10 users chatting)
ab -n 100 -c 10 http://localhost:8000/api/chat/sessions
```

---

## 📚 Additional Resources

- **OpenAI Streaming**: https://platform.openai.com/docs/api-reference/chat/create#chat/create-stream
- **Django Streaming**: https://docs.djangoproject.com/en/4.2/ref/request-response/#streaminghttp​response
- **NDJSON Format**: http://ndjson.org/
- **Anthropic Claude**: https://docs.anthropic.com/en/api/messages
- **Tool Use Pattern**: https://platform.openai.com/docs/guides/function-calling

---

## 💡 Pro Tips

1. **Start with OpenAI**: Easier API, more examples. Move to Anthropic after MVP.

2. **Use streaming from day 1**: Users expect fast feedback. Non-streaming feels slow.

3. **Test RBAC early**: Doctor accessing patient data should trigger audit. Verify this works.

4. **Set token limits**: Cap cost per user/day to prevent accidents:
   ```python
   if user_tokens_today > 1_000_000:
       return {"error": "Daily token limit reached"}
   ```

5. **Monitor costs immediately**: Set up daily cost reports:
   ```python
   total_cost = TokenUsageLog.objects.filter(
       created_at__date=today
   ).aggregate(Sum('estimated_cost'))['estimated_cost__sum']
   
   if total_cost > DAILY_BUDGET:
       alert_admin(f"Cost: ${total_cost}")
   ```

6. **Keep chat history trimmed**: Don't send entire chat history to LLM every time:
   ```python
   # Only send last 20 messages, not all 1000
   context = ChatContextManager.get_conversation_context(session, limit=20)
   ```

7. **Test tool calling thoroughly**: LLMs can hallucinate tool calls:
   ```python
   # Validate tool exists before calling
   if tool_name not in AVAILABLE_TOOLS:
       return error("Unknown tool")
   ```

---

## Next Steps

1. **Read** `FRONTEND_IMPLEMENTATION_GUIDE.md` (this folder) for detailed code
2. **Start** with `frontend/llm_handler.py` - most critical file
3. **Test** each endpoint with curl before building UI
4. **Choose** frontend stack (htmx = faster, React = more flexible)
5. **Deploy** to staging first, test with real LLM API
6. **Monitor** token usage and costs from day 1

**Estimated timeline**: 2-3 weeks for MVP, 4-6 weeks for production-ready.

Good luck! 🚀
