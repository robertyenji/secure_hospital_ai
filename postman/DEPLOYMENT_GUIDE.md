# 🚀 DEPLOYMENT & GO-LIVE GUIDE

## Implementation Complete! ✅

Your Secure Hospital AI LLM chatbot has been **fully implemented**. This guide walks you through deployment.

---

## Before You Start: Verify Implementation

### Files Check
Run this command to verify all files are in place:
```bash
cd c:\Users\rober\Desktop\dev\secure_hospital_ai

# Check models
Test-Path frontend\models.py  # Should have ChatSession & ChatMessage

# Check views
Test-Path frontend\views.py   # Should have 4 new endpoints (190+ lines)

# Check migrations
Test-Path frontend\migrations\0001_initial.py  # Should exist

# Check frontend
Test-Path frontend\templates\dashboard.html    # Should have chat UI

# Check LLM handler
Test-Path frontend\llm_handler.py              # Should be 689 lines
```

---

## 5-Minute Startup

### 1. Install Python Packages (2 min)
```powershell
cd c:\Users\rober\Desktop\dev\secure_hospital_ai

# Install required packages
pip install djangorestframework djangorestframework-simplejwt openai anthropic
```

### 2. Set LLM API Key (1 min)
Edit `.env` file and update:
```env
# Find this section:
LLM_PROVIDER=openai
LLM_MODEL=gpt-4-turbo
LLM_API_KEY=your-openai-api-key-here

# Replace "your-openai-api-key-here" with your actual OpenAI key
# Key should look like: sk-proj-...
```

### 3. Apply Database Migrations (1 min)
```powershell
python manage.py migrate
```

### 4. Start Development Server (1 min)
```powershell
python manage.py runserver
```

---

## Testing the Implementation

### Step 1: Login
- Open browser: `http://localhost:8000`
- Login with your Django user credentials

### Step 2: Create a Chat
- Click "+ New Chat" button
- Enter chat title (optional)
- Press OK

### Step 3: Send a Message
- Type your question in the input field
- Press Send or Enter

### Step 4: Verify Response
- Should see LLM response appear
- Token count should be displayed
- Message should be saved to history

### Step 5: Check Persistence
- Refresh the browser (Ctrl+R)
- Sessions should still be listed
- Chat history should still appear
- No data should be lost

---

## Understanding What's Running

```
┌─────────────────────────┐
│  Your Browser           │
│  http://localhost:8000  │
│  - Chat UI              │
│  - Session management   │
└──────────┬──────────────┘
           │ HTTP + CSRF
           ▼
┌─────────────────────────────────────┐
│ Django Server (localhost:8000)      │
│                                     │
│ Views (frontend/views.py):          │
│  - mcp_proxy (tool calls)           │
│  - chat_session_create              │
│  - chat_sessions_list               │
│  - chat_message_send                │
│  - chat_history                     │
│                                     │
│ Models (frontend/models.py):        │
│  - ChatSession                      │
│  - ChatMessage                      │
│  - Audit logs                       │
└──────────┬──────────────────────────┘
           │ REST API
           ▼
┌─────────────────────────────────────┐
│ LLM Handler (frontend/llm_handler.py)│
│ - Role-based prompts                │
│ - Tool filtering                    │
│ - Response streaming                │
│ - Error handling                    │
└──────────┬──────────────────────────┘
           │ JSON-RPC
           ▼
┌─────────────────────────────────────┐
│ LLM Provider (OpenAI/Claude/Azure)  │
│ - gpt-4-turbo (OpenAI)              │
│ - claude-3.5-sonnet (Anthropic)     │
│ - gpt-4 (Azure OpenAI)              │
└─────────────────────────────────────┘
```

---

## Testing with cURL

### Get CSRF Token First
```bash
# Save cookies
$response = Invoke-WebRequest -Uri "http://localhost:8000/api/chat/sessions/" -SessionVariable session

# Extract CSRF token
$csrf = $response.InputFields | Where-Object {$_.name -eq 'csrfmiddlewaretoken'} | Select-Object -ExpandProperty Value
```

### Test 1: Create Session
```bash
$headers = @{
    'Content-Type' = 'application/json'
    'X-CSRFToken' = $csrf
}

$body = @{
    title = "Test Chat"
    context = @{}
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/api/chat/session/" `
  -Method POST `
  -Headers $headers `
  -Body $body `
  -WebSession $session
```

### Test 2: List Sessions
```bash
Invoke-WebRequest -Uri "http://localhost:8000/api/chat/sessions/?limit=10" `
  -WebSession $session | Select-Object -ExpandProperty Content
```

### Test 3: Send Message
```bash
$body = @{
    session_id = 1
    message = "What is my role in the system?"
    stream = $false
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:8000/api/chat/message/" `
  -Method POST `
  -Headers $headers `
  -Body $body `
  -WebSession $session
```

---

## Monitoring & Troubleshooting

### Check Django Logs
Watch the terminal where you ran `python manage.py runserver`. You'll see:
```
GET /api/chat/sessions/ 200 ✓ (Good!)
POST /api/chat/message/ 200 ✓ (Good!)
POST /api/chat/message/ 500 ✗ (Error - check details)
```

### Check Browser Console
1. Open browser DevTools (F12)
2. Go to Console tab
3. Look for red errors
4. Common issues:
   - CSRF token mismatch → Check .env
   - API 404 → Wrong URL → Check urls.py
   - JSON parse error → Backend returned invalid JSON

### Check Database
```bash
# Connect to PostgreSQL
psql -h hopsserver001.postgres.database.azure.com -U robert -d clinic002

# Check tables exist
\dt frontend_*

# Check data
SELECT * FROM frontend_chatsession LIMIT 5;
SELECT * FROM frontend_chatmessage LIMIT 5;
```

### Common Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| "No module named 'rest_framework'" | Missing package | `pip install djangorestframework` |
| "LLM API Timeout" | Slow API response | Increase `LLM_TIMEOUT` in .env |
| "CSRF token missing" | Token not sent | Check `.env` has `DJANGO_SETTINGS_MODULE` |
| "404 Not Found" | Wrong URL | Check `frontend/urls.py` has new routes |
| "Session not found" | Wrong session ID | Use correct session ID from create endpoint |
| "Permission denied" | Role-based access | Different role can't see tool |

---

## Staging Deployment

### Requirements
- Python 3.10+ installed
- PostgreSQL database (Azure or local)
- OpenAI API key (or Anthropic/Azure)
- Git for version control

### Steps

1. **Clone Repository**
```bash
git clone https://github.com/yourusername/secure_hospital_ai.git
cd secure_hospital_ai
```

2. **Setup Virtual Environment**
```bash
python -m venv venv
venv\Scripts\activate
```

3. **Install Dependencies**
```bash
pip install -r requirements.txt
# Or: pip install django djangorestframework djangorestframework-simplejwt django-cors-headers python-dotenv requests openai anthropic psycopg2-binary
```

4. **Configure Environment**
```bash
# Copy .env template
cp .env.example .env

# Edit .env with your values
# - DATABASE_URL
# - LLM_API_KEY
# - JWT_SECRET
```

5. **Run Migrations**
```bash
python manage.py migrate
```

6. **Collect Static Files**
```bash
python manage.py collectstatic --noinput
```

7. **Start Server**
```bash
# Development (localhost only)
python manage.py runserver

# Production (exposed to network)
gunicorn secure_hospital_ai.wsgi:application --bind 0.0.0.0:8000
```

---

## Production Deployment Checklist

Before going live, complete these:

### Security
- [ ] Set `DEBUG=False` in Django settings
- [ ] Update `SECRET_KEY` to random secure value
- [ ] Set `ALLOWED_HOSTS` to production domain
- [ ] Enable HTTPS/SSL (nginx/Apache)
- [ ] Update `CSRF_TRUSTED_ORIGINS` for your domain
- [ ] Set `SESSION_SECURE_COOKIE=True`
- [ ] Set `SECURE_SSL_REDIRECT=True`
- [ ] Review all environment variables

### Database
- [ ] Database backup configured
- [ ] Automated daily backups running
- [ ] Tested restore procedure
- [ ] Connection pooling configured
- [ ] Query timeouts set appropriately

### Monitoring
- [ ] Error tracking setup (Sentry)
- [ ] Performance monitoring (DataDog/NewRelic)
- [ ] Log aggregation (CloudWatch/Splunk)
- [ ] Uptime monitoring (UptimeRobot)
- [ ] Alerts configured for:
  - [ ] Server down
  - [ ] High error rate
  - [ ] API timeout
  - [ ] Database connection issues
  - [ ] LLM API failures

### Application
- [ ] Load test passed (100+ concurrent users)
- [ ] Rate limiting configured
- [ ] Cost alerts setup (LLM API)
- [ ] Daily quota limits set
- [ ] Session timeouts configured
- [ ] CORS properly configured

### Documentation
- [ ] README.md updated
- [ ] API documentation generated
- [ ] Runbooks created for common issues
- [ ] Disaster recovery plan tested
- [ ] Team trained on deployment

### Compliance
- [ ] Security audit completed
- [ ] HIPAA compliance verified
- [ ] Penetration testing done
- [ ] Audit logs verified
- [ ] Data retention policy set
- [ ] PII handling documented

---

## Performance Optimization (Later)

### Database
```sql
-- Add indexes for common queries
CREATE INDEX idx_chatmessage_user_session ON frontend_chatmessage(session_id, created_at);
CREATE INDEX idx_auditlog_user_timestamp ON audit_auditlog(user_id, timestamp DESC);
```

### Caching
```python
# In views.py
from django.views.decorators.cache import cache_page

@cache_page(60 * 5)  # Cache for 5 minutes
def chat_sessions_list(request):
    ...
```

### Pagination
```python
# Already implemented in chat_history
# Adjust limits in views.py:
limit = int(request.query_params.get('limit', 50))  # Default 50, max 100
```

### Static Files
```bash
# Serve static files efficiently in production
python manage.py collectstatic --clear --noinput

# Use nginx to serve static files for speed
# See nginx.conf in repo
```

---

## Rollback Plan

If something goes wrong:

### Quick Rollback
```bash
# 1. Stop current server
# Press Ctrl+C in terminal

# 2. Go to previous commit
git checkout HEAD~1

# 3. Reinstall packages
pip install -r requirements.txt

# 4. Reverse migrations
python manage.py migrate frontend 0

# 5. Restart server
python manage.py runserver
```

### Database Rollback
```bash
# If migrations caused issues:
python manage.py migrate frontend 0001_initial  # Go to specific migration
python manage.py migrate                         # Reapply

# Or restore from backup:
# Contact your database administrator
```

---

## Success Metrics

Track these after going live:

### Usage
- Users creating sessions per day
- Messages sent per day
- Average session length
- Peak concurrent users

### Performance
- Average response time (goal: < 5 sec)
- API 99th percentile latency
- Database query time
- LLM API latency

### Quality
- Error rate (goal: < 0.1%)
- RBAC violations blocked
- Messages properly redacted
- Audit logs comprehensive

### Cost
- LLM API cost per user
- Database storage growth
- Infrastructure cost
- Support tickets

---

## Support & Escalation

### Level 1: Developer
- Check logs (Django console)
- Check browser console (F12)
- Review error messages
- Test with cURL

### Level 2: DevOps
- Check server health
- Check database connection
- Check API rate limits
- Review monitoring dashboards

### Level 3: Vendor
- Contact OpenAI support (API issues)
- Contact Azure support (infrastructure)
- Contact AWS/GCP support (cloud)

---

## Next Steps After Launch

### Week 1
- [ ] Monitor error rates
- [ ] Check user feedback
- [ ] Review performance metrics
- [ ] Verify RBAC enforcement
- [ ] Check audit logs

### Week 2-4
- [ ] Optimize slow queries
- [ ] Fine-tune LLM prompts
- [ ] Add usage analytics
- [ ] Scale if needed
- [ ] Plan feature improvements

### Month 2
- [ ] Review cost optimization
- [ ] Consider streaming responses
- [ ] Implement conversation templates
- [ ] Add advanced search
- [ ] Plan React upgrade

---

## You're Ready! 🎉

Your implementation is complete. Follow the 5-minute startup guide above and you'll be live!

**Questions?** Review the documentation files:
- IMPLEMENTATION_COMPLETE.md - Full guide
- IMPLEMENTATION_STATUS.md - What was built
- QUICK_REFERENCE.md - Quick overview

**Let's deploy!** 🚀
