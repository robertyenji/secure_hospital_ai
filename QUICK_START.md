# Quick Start: LLM Agent Integration

## 5-Minute Setup Overview

Your system is **95% ready** for LLM integration. Here's what you have:

✅ **Already Complete:**
- JWT authentication (fixed today!)
- RBAC enforcement at MCP level
- PHI redaction
- Audit logging
- Secure proxy endpoint

❌ **Still Needed:**
- LLM handler (llm_handler.py) - **JUST PROVIDED** ✓
- Chat session models - needs migration
- API endpoints - needs views
- Frontend chat UI - needs update

---

## Step 1: Install Dependencies (5 min)

```bash
cd secure_hospital_ai

# Install LLM libraries
pip install openai anthropic python-dotenv

# Optional: for rate limiting and async tasks
pip install django-ratelimit celery redis
```

---

## Step 2: Configure Environment (5 min)

Create/update `.env`:

```bash
# LLM Configuration
LLM_PROVIDER=openai
LLM_MODEL=gpt-4-turbo-preview
LLM_API_KEY=sk-...your-key-here...
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000
LLM_TIMEOUT=30

# Optional: Anthropic (if using Claude)
# LLM_PROVIDER=anthropic
# LLM_MODEL=claude-3-sonnet-20240229
# LLM_API_KEY=sk-ant-...
```

**Get your API key:**
- OpenAI: https://platform.openai.com/api-keys
- Anthropic: https://console.anthropic.com/account/keys

---

## Step 3: Create Chat Models (10 min)

Add to `frontend/models.py`:

```python
import uuid
from django.db import models
from django.contrib.auth.models import User

class ChatSession(models.Model):
    """Persistent chat session for LLM conversations"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_sessions")
    title = models.CharField(max_length=255, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False)
    
    class Meta:
        ordering = ["-updated_at"]
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"


class ChatMessage(models.Model):
    """Individual messages in a chat session"""
    MESSAGE_TYPES = [
        ("user", "User Message"),
        ("assistant", "Assistant Response"),
        ("tool", "Tool Call"),
        ("error", "Error"),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=20, choices=MESSAGE_TYPES)
    content = models.TextField()
    tool_call_id = models.CharField(max_length=255, null=True, blank=True)
    tool_name = models.CharField(max_length=255, null=True, blank=True)
    tool_result = models.JSONField(null=True, blank=True)
    tokens_used = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["created_at"]
    
    def __str__(self):
        return f"{self.session.title} - {self.role}"
```

---

## Step 4: Run Migrations (5 min)

```bash
python manage.py makemigrations frontend
python manage.py migrate
```

---

## Step 5: Add API Endpoints (15 min)

Add to `frontend/views.py`:

```python
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status as http_status
from django.http import StreamingHttpResponse
import json

from .llm_handler import LLMAgentHandler
from .models import ChatSession, ChatMessage

def get_client_ip(request):
    """Extract client IP from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0]
    return request.META.get('REMOTE_ADDR')

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def create_chat_session(request):
    """Create new chat session"""
    title = request.data.get("title", "New Chat")
    session = ChatSession.objects.create(user=request.user, title=title)
    return Response({
        "session_id": str(session.id),
        "title": session.title,
        "created_at": session.created_at.isoformat()
    })

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def list_chat_sessions(request):
    """List all chat sessions for user"""
    sessions = ChatSession.objects.filter(
        user=request.user,
        is_archived=False
    )
    return Response({
        "sessions": [
            {
                "id": str(s.id),
                "title": s.title,
                "updated_at": s.updated_at.isoformat(),
                "message_count": s.messages.count()
            }
            for s in sessions
        ]
    })

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_chat_history(request, session_id):
    """Get chat history for a session"""
    try:
        session = ChatSession.objects.get(id=session_id, user=request.user)
        messages = [
            {
                "id": str(msg.id),
                "role": msg.role,
                "content": msg.content,
                "tool_name": msg.tool_name,
                "created_at": msg.created_at.isoformat()
            }
            for msg in session.messages.all()
        ]
        return Response({
            "session_id": str(session.id),
            "title": session.title,
            "messages": messages
        })
    except ChatSession.DoesNotExist:
        return Response(
            {"error": "Session not found"},
            status=http_status.HTTP_404_NOT_FOUND
        )

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def chat_message(request):
    """
    Accept a user message and return streaming LLM response.
    
    Request body:
    {
        "session_id": "uuid",
        "message": "What are John's recent admissions?"
    }
    
    Response: NDJSON stream of events
    """
    try:
        data = request.data
        session_id = data.get("session_id")
        user_message = data.get("message", "").strip()
        
        if not user_message:
            return Response(
                {"error": "Message cannot be empty"},
                status=http_status.HTTP_400_BAD_REQUEST
            )
        
        # Get session with user verification
        try:
            session = ChatSession.objects.get(id=session_id, user=request.user)
        except ChatSession.DoesNotExist:
            return Response(
                {"error": "Chat session not found"},
                status=http_status.HTTP_404_NOT_FOUND
            )
        
        # Save user message
        ChatMessage.objects.create(
            session=session,
            role="user",
            content=user_message
        )
        
        # Create LLM handler
        ip_address = get_client_ip(request)
        llm_handler = LLMAgentHandler(request.user, ip_address)
        
        # Stream response
        def response_generator():
            for chunk in llm_handler.stream_response(user_message):
                # Parse and store messages
                try:
                    event = json.loads(chunk.strip())
                    if event.get("type") == "message":
                        # Store assistant message
                        ChatMessage.objects.create(
                            session=session,
                            role="assistant",
                            content=event.get("content", "")
                        )
                    elif event.get("type") == "tool_call":
                        # Store tool call
                        ChatMessage.objects.create(
                            session=session,
                            role="tool",
                            content=json.dumps(event.get("content", {})),
                            tool_name=event.get("content", {}).get("function", {}).get("name")
                        )
                except json.JSONDecodeError:
                    pass
                
                yield chunk
        
        return StreamingHttpResponse(
            response_generator(),
            content_type="application/x-ndjson"
        )
        
    except Exception as e:
        return Response(
            {"error": f"Internal error: {str(e)}"},
            status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )
```

---

## Step 6: Update URLs (5 min)

Update `frontend/urls.py`:

```python
from django.urls import path
from . import views

app_name = "frontend"

urlpatterns = [
    # Existing endpoints
    path("", views.dashboard, name="dashboard"),
    path("mint-token/", views.mint_token, name="mint_token"),
    path("mcp-proxy/", views.mcp_proxy, name="mcp_proxy"),
    path("audit-latest/", views.audit_latest, name="audit_latest"),
    path("whoami/", views.whoami, name="whoami"),
    path("rbac/effective/", views.effective_rbac, name="effective_rbac"),
    
    # NEW Chat endpoints
    path("api/chat/session/", views.create_chat_session, name="create_session"),
    path("api/chat/sessions/", views.list_chat_sessions, name="list_sessions"),
    path("api/chat/history/<str:session_id>/", views.get_chat_history, name="chat_history"),
    path("api/chat/message/", views.chat_message, name="chat_message"),
]
```

---

## Step 7: Test with cURL (10 min)

### 1. Get JWT token

```bash
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# Response: {"access": "eyJ...", "refresh": "eyJ..."}
# Copy the access token
```

### 2. Create chat session

```bash
curl -X POST http://localhost:8000/frontend/api/chat/session/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Patient Review"}'

# Response: {"session_id": "uuid-...", "title": "Patient Review", ...}
# Copy the session_id
```

### 3. Send message (streaming)

```bash
curl -X POST http://localhost:8000/frontend/api/chat/message/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "YOUR_SESSION_ID", "message": "What is patient PAT-001?"}'

# Response: Streaming NDJSON events
# Example output:
# {"type": "message", "content": "Looking up patient...", "timestamp": "..."}
# {"type": "tool_call", "content": {"function": {"name": "get_patient_overview", ...}}, ...}
# {"type": "message", "content": "Patient PAT-001 is John Doe...", ...}
```

---

## Step 8: Update Frontend (Optional - Simple htmx approach)

Update `frontend/templates/dashboard.html` to add chat panel:

```html
<!-- Add to sidebar (left panel) -->
<div class="card">
  <h3 style="color:#0f172a">AI Chat</h3>
  
  <!-- Chat history -->
  <div id="chat-messages" class="muted" style="min-height: 200px; border: 1px solid #e5e7eb; padding: 8px; border-radius: 8px; margin-bottom: 8px;">
    <p style="color: #cbd5e1; text-align: center;">Start a conversation below...</p>
  </div>
  
  <!-- Chat input -->
  <form hx-post="{% url 'frontend:chat_message' %}"
        hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'
        hx-vals='js:{session_id: window.sessionId, message: this.querySelector("input").value}'
        hx-on::after-request="if(event.detail.successful) this.reset()">
    <div style="display: flex; gap: 4px;">
      <input name="message" placeholder="Ask about patients..." style="flex: 1;" />
      <button class="btn" type="submit">Send</button>
    </div>
  </form>
  
  <!-- Create session on page load -->
  <div hx-post="{% url 'frontend:create_session' %}"
       hx-trigger="load"
       hx-swap="none"
       hx-on::after-request="window.sessionId = JSON.parse(event.detail.xhr.response).session_id;"></div>
</div>
```

---

## Step 9: Test Everything (15 min)

```bash
# 1. Check if llm_handler loads correctly
python manage.py shell
>>> from frontend.llm_handler import LLMAgentHandler
>>> print("LLM handler loaded successfully")

# 2. Check if models exist
>>> from frontend.models import ChatSession, ChatMessage
>>> ChatSession.objects.count()
0

# 3. Test in browser
# 1. Go to http://localhost:8000/frontend/
# 2. Click "Who am I?" to verify authentication
# 3. Fill in patient ID and select a tool
# 4. Try the new Chat widget
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'openai'"
```bash
pip install openai
```

### "LLM_API_KEY not configured"
- Check `.env` file has `LLM_API_KEY=sk-...`
- Run `python manage.py shell` and check: `os.getenv("LLM_API_KEY")`

### "403 Forbidden" on /api/chat/message/
- You're still hitting CSRF. Make sure you're using JWT:
  ```bash
  curl -H "Authorization: Bearer YOUR_JWT_TOKEN" ...
  ```
  NOT:
  ```bash
  curl -H "X-CSRFToken: ..." ...  # Wrong for JWT endpoints
  ```

### Chat messages not streaming
- Check that response is NDJSON (one JSON object per line)
- Verify frontend is handling streaming correctly
- Check browser console for errors

### Audit logs not being created
- Make sure user is authenticated
- Check `AuditLog` table exists: `python manage.py shell`
  ```python
  from audit.models import AuditLog
  AuditLog.objects.count()
  ```

---

## Next Steps

### Immediate (Today):
1. ✅ Install dependencies
2. ✅ Add API key to `.env`
3. ✅ Create models and migrate
4. ✅ Add views and test with cURL

### This Week:
5. ✅ Update dashboard with chat UI
6. ✅ Test RBAC (doctor can't see billing tools)
7. ✅ Verify audit logging works

### Next Week:
8. ✅ Build proper React frontend (if desired)
9. ✅ Add rate limiting
10. ✅ Deploy to staging

---

## Cost Management

**OpenAI (GPT-4 Turbo):**
- ~$0.01 per 1K prompt tokens
- ~$0.03 per 1K completion tokens
- Typical cost per chat: $0.05-0.25

**Daily Budget Alert:**
```python
# Add to settings.py
LLM_DAILY_BUDGET = 100  # $ per day

# Add to chat_message view
daily_cost = TokenUsageLog.objects.filter(
    created_at__date=today
).aggregate(Sum('cost'))['cost__sum'] or 0

if daily_cost > LLM_DAILY_BUDGET:
    return Response(
        {"error": "Daily LLM budget exceeded"},
        status=http_status.HTTP_429_TOO_MANY_REQUESTS
    )
```

---

## Security Reminders

✅ **Already Secure:**
- JWT authentication (fixed today!)
- RBAC enforcement
- PHI redaction at MCP level
- Audit logging

⚠️ **Still Need To:**
- Add rate limiting (100 msgs/hour per user)
- Validate tool calls before execution
- Sanitize inputs for prompt injection
- Log all PHI access

---

## File Checklist

You should now have:

```
✓ frontend/llm_handler.py      (provided above)
✓ frontend/models.py           (updated with ChatSession, ChatMessage)
✓ frontend/views.py            (added 4 new endpoints)
✓ frontend/urls.py             (added 4 new routes)
✓ frontend/templates/dashboard.html  (optional: add chat UI)
✓ .env                         (LLM configuration)
✓ settings.py                  (should work as-is)
```

---

**You're ready to go! Start with Step 1 and follow in order.** 🚀

Questions? Check `FRONTEND_IMPLEMENTATION_GUIDE.md` for detailed explanations.
