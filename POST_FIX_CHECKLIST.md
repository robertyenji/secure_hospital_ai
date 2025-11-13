# ✅ Implementation Checklist - POST-FIX

## 🎯 What Needs to Happen Now

### Phase 1: Install & Restart (5 minutes)

- [ ] **Install OpenAI Package**
  ```bash
  pip install --upgrade openai
  ```
  - Verify: `pip list | grep openai` should show version >= 1.0.0
  - Why: Code uses new API syntax from v1.0.0+

- [ ] **Restart Django Server**
  ```bash
  python manage.py runserver
  ```
  - Verify: No import errors in console
  - Why: Python needs to reload updated modules

- [ ] **Clear Browser Cache**
  - Open DevTools (F12) → Application → Cache Storage → Clear all
  - Why: Ensure fresh JavaScript is loaded
  - Or: Hard refresh with Ctrl+Shift+R

---

### Phase 2: Verify Fixes (5 minutes)

- [ ] **Check Token Minting**
  1. Open `http://localhost:8000`
  2. Open DevTools Console (F12)
  3. Should see: `✅ Token minted for [username] (role: [role])`
  4. If not: Check that `/mint-token/` returns JSON with `token` field

- [ ] **Verify No 401 Errors**
  1. Open DevTools Network tab (F12)
  2. Click "+ New Chat"
  3. Check POST request to `/api/chat/session/`
  4. Should be: `201 Created` (not 401 Unauthorized)
  5. Request Headers should have: `Authorization: Bearer eyJ0...`

- [ ] **Verify No 500 Errors**
  1. Type a message and click Send
  2. Check POST request to `/api/chat/message/`
  3. Should be: `200 OK` (not 500 Internal Server Error)
  4. If error, check:
     - OpenAI package installed
     - LLM_API_KEY set in .env
     - Django console for detailed error

---

### Phase 3: Test Chat Functionality (10 minutes)

- [ ] **Create First Chat**
  1. Click "+ New Chat" button
  2. Enter title (e.g., "Test Chat")
  3. Chat appears in sidebar
  4. Messages area is empty and ready

- [ ] **Send Message**
  1. Type: "What is your name?"
  2. Click Send
  3. Message appears in blue (user) on right
  4. Status shows: "⏳ Waiting for response..."

- [ ] **Receive Response**
  1. Wait 5-10 seconds for LLM response
  2. Response appears in light blue (assistant) on left
  3. Token count displayed below message
  4. Status clears

- [ ] **Check History**
  1. Select another session or create new one
  2. Click back on first chat
  3. Previous messages should still be there
  4. Full conversation history loads

- [ ] **Multiple Sessions**
  1. Create 2-3 different chat sessions
  2. Each appears in sidebar
  3. Can switch between them
  4. Each has independent history

---

### Phase 4: Check Logs & Errors (5 minutes)

- [ ] **Django Server Logs**
  - Terminal where runserver is running should show:
    ```
    ✅ Request lines for /api/chat/session/ → 201
    ✅ Request lines for /api/chat/message/ → 200
    ✅ NO "401 Unauthorized" messages
    ✅ NO "500 Internal Server Error" messages
    ```

- [ ] **Browser Console**
  - DevTools Console (F12) should be clean:
    ```
    ✅ "✅ Token minted for..."
    ✅ No red error messages
    ✅ No "401 Unauthorized" warnings
    ```

- [ ] **Network Tab**
  - All API calls should succeed:
    ```
    ✅ GET /mint-token/ → 200
    ✅ POST /api/chat/session/ → 201
    ✅ GET /api/chat/sessions/ → 200
    ✅ POST /api/chat/message/ → 200
    ✅ GET /api/chat/history/ → 200
    ```

---

## 🔍 Troubleshooting Checklist

### If You See: 401 Unauthorized

- [ ] Check JWT token minting:
  ```bash
  curl http://localhost:8000/mint-token/
  # Should return: {"ok": true, "token": "..."}
  ```

- [ ] Verify Authorization header is being sent:
  1. DevTools Network tab
  2. Click on API request
  3. Headers section
  4. Look for: `Authorization: Bearer eyJ0...`

- [ ] Refresh page and try again:
  ```
  Ctrl + Shift + R (hard refresh)
  ```

### If You See: 500 Internal Server Error on /api/chat/message/

- [ ] **Check OpenAI installation:**
  ```bash
  python -c "from openai import OpenAI; print('OK')"
  # Should print: OK
  ```

- [ ] **Check LLM API key:**
  ```bash
  python -c "import os; print('Key set:' if os.getenv('LLM_API_KEY') else 'Key missing')"
  ```

- [ ] **Check .env file:**
  - Open `.env` file
  - Verify: `LLM_API_KEY=sk-proj-...` (your real key)
  - Not: `LLM_API_KEY=your-key-here`

- [ ] **Restart Django after .env changes:**
  ```bash
  python manage.py runserver
  ```

### If Chat Loads But No Response

- [ ] **Check if LLM_API_KEY is valid:**
  ```bash
  python manage.py shell
  >>> from openai import OpenAI
  >>> client = OpenAI(api_key="your_key_here")
  >>> client.models.list()
  # If this works, key is valid
  ```

- [ ] **Check server logs for detailed errors:**
  - Look at terminal where Django is running
  - Should show error details

- [ ] **Try a simple test:**
  ```bash
  python manage.py shell
  >>> from frontend.llm_handler import LLMAgentHandler, LLMConfig
  >>> LLMConfig.validate()
  # Should print: "LLM configured: openai / gpt-4-turbo"
  ```

### If "+ New Chat" Button Doesn't Work

- [ ] **Check for JavaScript errors:**
  1. DevTools Console (F12)
  2. Look for red error messages
  3. Report the error message

- [ ] **Check mint_token endpoint:**
  ```bash
  curl http://localhost:8000/mint-token/
  ```
  - Should return JWT token

- [ ] **Verify JavaScript is loaded:**
  1. DevTools Network tab
  2. Check that `dashboard.html` loaded
  3. Check for any failed JS file loads

---

## 📊 Success Checklist

You'll know everything is working when:

- [x] ✅ OpenAI package installed (v1.0.0+)
- [x] ✅ Django server restarted
- [x] ✅ Browser console shows: `✅ Token minted for...`
- [x] ✅ No 401 Unauthorized errors on /api/chat/session/
- [x] ✅ No 401 Unauthorized errors on /api/chat/sessions/
- [x] ✅ No 500 errors on /api/chat/message/
- [x] ✅ Can create new chat sessions
- [x] ✅ Can send messages
- [x] ✅ LLM responds to messages
- [x] ✅ Chat history persists
- [x] ✅ Can switch between chat sessions

---

## 📝 Summary of Changes

### Code Changes Made
- ✅ `frontend/llm_handler.py` - Updated OpenAI API calls
- ✅ `frontend/templates/dashboard.html` - Added JWT token handling
- ✅ `frontend/views.py` - Enhanced mint_token endpoint

### Installation Required
- ✅ `pip install --upgrade openai` - Must do this!

### Configuration Required
- ✅ `.env` file - Must have valid LLM_API_KEY

### Testing Required
- ✅ Create chat session
- ✅ Send message
- ✅ Verify LLM response

---

## 🚀 Ready to Go!

**Next Step:** Run the installation command and restart Django

```bash
# Step 1: Install OpenAI
pip install --upgrade openai

# Step 2: Restart Django
python manage.py runserver

# Step 3: Test in browser
# Open http://localhost:8000
```

---

**Status:** ✅ **READY TO DEPLOY & TEST**

All code fixes are in place. Just install the package and restart!
