# Frontend Implementation Guide – LLM Agent Integration

## Executive Summary

Your current frontend demonstrates the core MCP proxy pattern with htmx and Django templates. It successfully:

✅ **Working Well:**
- JWT authentication via `/mint-token/` endpoint
- RBAC enforcement at MCP server level
- Quick Tools UI for testing individual tools
- Raw JSON-RPC sender for direct MCP testing
- Audit log visibility per user
- CSRF token handling corrected (now uses JWT decorators)

⚠️ **Needs Improvement Before LLM Integration:**
- No persistent chat history or conversation memory
- No streaming response support (LLM responses can be large/slow)
- No token usage tracking or cost estimation
- No error recovery or retry logic
- No loading states or UX polish for async operations
- No prompt templates or system message management
- Frontend/backend separation unclear for LLM integration point
- No session management beyond single page load

---

## Architecture Recommendation: Hybrid REST + WebSocket Approach

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React/Vue)                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Chat Interface                                        │ │
│  │  - Message history                                    │ │
│  │  - Streaming responses                                │ │
│  │  - Tool call visualization                            │ │
│  │  - Error handling & retry UI                          │ │
│  └────────────────────────────────────────────────────────┘ │
│           ↓ REST API + WebSocket                            │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│           Django Backend (New LLM Handler)                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ /api/chat/message         - New chat message          │ │
│  │ /api/chat/history         - Load conversation         │ │
│  │ /api/chat/ws              - WebSocket stream          │ │
│  │ /api/chat/context         - Relevant context data     │ │
│  └────────────────────────────────────────────────────────┘ │
│           ↓ JWT Auth + Session Context                      │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│        LLM Agent Handler (New Module)                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ - LLM API calls (OpenAI, Claude, etc.)               │ │
│  │ - Prompt template management                         │ │
│  │ - Tool binding & validation                          │ │
│  │ - Response streaming                                 │ │
│  │ - Error recovery                                     │ │
│  └────────────────────────────────────────────────────────┘ │
│           ↓ MCP Protocol                                    │
└─────────────────────────────────────────────────────────────┘
           ↓
┌─────────────────────────────────────────────────────────────┐
│        FastAPI MCP Server (Already Implemented)             │
│  ✓ RBAC + JWT validation                                  │
│  ✓ PHI redaction                                          │
│  ✓ Audit logging                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Implementation Plan

### Phase 1: Backend – LLM Agent Handler (Week 1-2)

**1.1 Create `llm_handler.py` module**

```python
# frontend/llm_handler.py
"""
LLM Agent Handler – manages LLM interactions with prompt templates,
tool binding, response streaming and error recovery.
"""

import os
import json
import openai
from enum import Enum
from typing import Optional, Dict, List, Iterator
from dataclasses import dataclass
from audit.models import AuditLog
from django.contrib.auth.models import User

class ToolType(Enum):
    PATIENT_OVERVIEW = "get_patient_overview"
    PATIENT_ADMISSIONS = "get_patient_admissions"
    PATIENT_APPOINTMENTS = "get_patient_appointments"
    PATIENT_RECORDS = "get_patient_records"
    MY_SHIFTS = "get_my_shifts"

@dataclass
class ToolCall:
    tool: str
    patient_id: Optional[str]
    reason: str  # Why did LLM choose this tool

class LLMConfig:
    """Configuration for LLM provider and model"""
    MODEL = os.getenv("LLM_MODEL", "gpt-4-turbo-preview")
    API_KEY = os.getenv("LLM_API_KEY", "")
    TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))

class SystemPromptManager:
    """Manages role-based system prompts for the LLM"""
    
    SYSTEM_PROMPTS = {
        "Admin": """You are a hospital administration assistant with full access to all systems.
You can view and modify patient records, staff information, admissions, and all sensitive data.
Your role is to help with administrative tasks and system management.
Always be professional and respect HIPAA guidelines even though you have full access.
""",
        "Doctor": """You are a hospital AI assistant supporting doctors.
You can view patient medical records, admissions, and appointments for your assigned patients.
You CANNOT view full PHI (SSN, full address, insurance details) - this is automatically redacted.
Help doctors with diagnoses, treatment planning and patient information retrieval.
Always recommend consulting the full patient record in the EHR system.
""",
        "Nurse": """You are a hospital AI assistant supporting nurses.
You can view patient information, admissions, appointments and care records for assigned patients.
PHI is redacted for security. You can help with shift management, patient monitoring and care coordination.
Recommend escalating complex medical decisions to doctors.
""",
        "Billing": """You are a billing department AI assistant.
You can access patient insurance information and billing-related data only.
You CANNOT view medical records or sensitive PHI beyond insurance details.
Help with claims, insurance verification and billing inquiries.
""",
        "Reception": """You are a reception desk AI assistant.
You can help with appointment scheduling, patient check-in and basic patient information.
You have minimal access to sensitive data. Escalate medical inquiries to appropriate staff.
""",
        "Auditor": """You are a compliance and audit AI assistant.
You can view all data including full audit logs and PHI for compliance purposes.
Your role is to help with compliance audits, access reviews and security analysis.
Always document your access for audit trails.
"""
    }

    @staticmethod
    def get_prompt(role: str) -> str:
        """Get system prompt for a user's role"""
        return SystemPromptManager.SYSTEM_PROMPTS.get(
            role, 
            SystemPromptManager.SYSTEM_PROMPTS["Reception"]  # Default to least privileged
        )

class LLMAgentHandler:
    """Main handler for LLM agent interactions"""
    
    def __init__(self, user: User, ip_address: str = ""):
        self.user = user
        self.ip_address = ip_address
        self.role = getattr(user, "role", "Reception")
        self.system_prompt = SystemPromptManager.get_prompt(self.role)
        
    def stream_response(self, user_message: str) -> Iterator[str]:
        """
        Stream LLM response with streaming support for long responses.
        
        Yields: JSON chunks with format
        {"type": "message" | "tool_call" | "error", "content": "..."}
        """
        try:
            # Build conversation context
            messages = [
                {
                    "role": "system",
                    "content": self.system_prompt
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ]
            
            # Define available tools based on role (RBAC)
            tools = self._get_available_tools()
            
            # Call LLM with streaming
            response_stream = openai.ChatCompletion.create(
                model=LLMConfig.MODEL,
                messages=messages,
                tools=tools,
                temperature=LLMConfig.TEMPERATURE,
                max_tokens=LLMConfig.MAX_TOKENS,
                timeout=LLMConfig.TIMEOUT,
                stream=True,
            )
            
            # Buffer for tool call assembly
            tool_call_buffer = ""
            
            for chunk in response_stream:
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                
                # Text content
                if "content" in delta and delta["content"]:
                    yield json.dumps({
                        "type": "message",
                        "content": delta["content"]
                    }) + "\n"
                
                # Tool call detection
                if "tool_calls" in delta:
                    for tool_call in delta["tool_calls"]:
                        tool_call_buffer += json.dumps(tool_call)
                        
                        # Once complete, validate and return
                        if self._is_valid_tool_call(tool_call_buffer):
                            yield json.dumps({
                                "type": "tool_call",
                                "content": json.loads(tool_call_buffer)
                            }) + "\n"
                            tool_call_buffer = ""
            
            # Log successful interaction
            self._log_audit("LLM_CALL", "LLM", None, False)
            
        except Exception as e:
            error_msg = f"LLM error: {str(e)}"
            yield json.dumps({
                "type": "error",
                "content": error_msg
            }) + "\n"
            
            # Log error
            self._log_audit("LLM_ERROR", "LLM", None, False)

    def _get_available_tools(self) -> List[Dict]:
        """
        Return available tools based on user's RBAC role.
        Tools are defined as OpenAI function_call schema.
        """
        base_tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_patient_overview",
                    "description": "Get overview of a patient",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "patient_id": {
                                "type": "string",
                                "description": "The patient ID (e.g., PAT-001)"
                            }
                        },
                        "required": ["patient_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_patient_admissions",
                    "description": "Get hospital admissions for a patient",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "patient_id": {
                                "type": "string",
                                "description": "The patient ID"
                            }
                        },
                        "required": ["patient_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_patient_appointments",
                    "description": "Get appointments for a patient",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "patient_id": {
                                "type": "string",
                                "description": "The patient ID"
                            }
                        },
                        "required": ["patient_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_patient_records",
                    "description": "Get medical records for a patient",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "patient_id": {
                                "type": "string",
                                "description": "The patient ID"
                            }
                        },
                        "required": ["patient_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_my_shifts",
                    "description": "Get your scheduled shifts",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        ]
        
        # Filter tools by role
        if self.role == "Auditor":
            # Auditors can use all tools
            return base_tools
        elif self.role == "Admin":
            # Admins can use most tools
            return base_tools
        elif self.role == "Doctor":
            # Doctors can use patient-focused tools
            return base_tools[:-1]  # All except shifts (they have their own endpoint)
        elif self.role == "Nurse":
            # Nurses similar to doctors
            return base_tools[:-1]
        else:
            # Billing & Reception have limited access
            return base_tools[:1]  # Only patient overview

    def _is_valid_tool_call(self, tool_call_json: str) -> bool:
        """Validate tool call format"""
        try:
            data = json.loads(tool_call_json)
            return "function" in data and "arguments" in data
        except:
            return False

    def _log_audit(self, action: str, table_name: str, record_id: Optional[str], is_phi: bool):
        """Log interaction to audit log"""
        AuditLog.objects.create(
            user=self.user,
            action=action,
            table_name=table_name,
            record_id=record_id,
            ip_address=self.ip_address,
            is_phi_access=is_phi
        )
```

**1.2 Create `chat_handler.py` for conversation management**

```python
# frontend/chat_handler.py
"""
Chat session and history management for LLM conversations.
"""

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

class ChatContextManager:
    """Manages context for LLM calls"""
    
    @staticmethod
    def get_session(user: User, session_id: str) -> ChatSession:
        """Get chat session with user verification"""
        return ChatSession.objects.get(id=session_id, user=user)
    
    @staticmethod
    def create_session(user: User, title: str = "New Chat") -> ChatSession:
        """Create new chat session"""
        return ChatSession.objects.create(user=user, title=title)
    
    @staticmethod
    def add_message(session: ChatSession, role: str, content: str, 
                   tool_name: str = None, tool_result: dict = None) -> ChatMessage:
        """Add message to session"""
        return ChatMessage.objects.create(
            session=session,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_result=tool_result
        )
    
    @staticmethod
    def get_conversation_context(session: ChatSession, limit: int = 20) -> List[Dict]:
        """Get conversation history for LLM context"""
        messages = []
        for msg in session.messages.all()[-limit:]:
            messages.append({
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.created_at.isoformat()
            })
        return messages
```

**1.3 Create new API endpoints in `views.py`**

Add these views to your existing `frontend/views.py`:

```python
# Add to frontend/views.py

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status as http_status
from django.http import StreamingHttpResponse
import json

from .llm_handler import LLMAgentHandler
from .chat_handler import ChatSession, ChatMessage, ChatContextManager

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
            session = ChatContextManager.get_session(request.user, session_id)
        except ChatSession.DoesNotExist:
            return Response(
                {"error": "Chat session not found"},
                status=http_status.HTTP_404_NOT_FOUND
            )
        
        # Save user message
        ChatContextManager.add_message(session, "user", user_message)
        
        # Create LLM handler
        ip_address = get_client_ip(request)
        llm_handler = LLMAgentHandler(request.user, ip_address)
        
        # Stream response
        def response_generator():
            for chunk in llm_handler.stream_response(user_message):
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

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def create_chat_session(request):
    """Create new chat session"""
    title = request.data.get("title", "New Chat")
    session = ChatContextManager.create_session(request.user, title)
    return Response({
        "session_id": str(session.id),
        "title": session.title,
        "created_at": session.created_at.isoformat()
    })

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def get_chat_history(request, session_id):
    """Get chat history for a session"""
    try:
        session = ChatContextManager.get_session(request.user, session_id)
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

def get_client_ip(request):
    """Extract client IP from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
```

---

### Phase 2: Frontend – React Chat Component (Week 2-3)

**2.1 Set up React with Vite**

```bash
# Install React + dependencies
npm install react react-dom vite @vitejs/plugin-react
npm install axios zustand markdown-it
npm install -D tailwindcss postcss autoprefixer
```

**2.2 Create Chat Component Structure**

```jsx
// frontend/static/components/Chat.jsx
import React, { useEffect, useState, useRef } from 'react';
import { ChatInput } from './ChatInput';
import { MessageList } from './MessageList';
import { Sidebar } from './Sidebar';
import { useChat } from '../hooks/useChat';

export function Chat() {
  const [sessionId, setSessionId] = useState(null);
  const [sessions, setSessions] = useState([]);
  const { messages, addMessage, loading } = useChat(sessionId);

  useEffect(() => {
    // Load sessions on mount
    loadSessions();
  }, []);

  const loadSessions = async () => {
    const response = await fetch('/api/chat/sessions', {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('access_jwt')}`
      }
    });
    const data = await response.json();
    setSessions(data.sessions);
    
    // Open first session or create new one
    if (data.sessions.length > 0) {
      setSessionId(data.sessions[0].id);
    } else {
      createNewSession();
    }
  };

  const createNewSession = async () => {
    const response = await fetch('/api/chat/session', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('access_jwt')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ title: 'New Chat' })
    });
    const data = await response.json();
    setSessionId(data.session_id);
    loadSessions();
  };

  const handleSendMessage = async (content) => {
    addMessage({
      role: 'user',
      content,
      timestamp: new Date().toISOString()
    });

    try {
      const response = await fetch('/api/chat/message', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('access_jwt')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          session_id: sessionId,
          message: content
        })
      });

      // Handle streaming response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (line.trim()) {
            const chunk = JSON.parse(line);
            if (chunk.type === 'message') {
              addMessage({
                role: 'assistant',
                content: chunk.content,
                timestamp: new Date().toISOString()
              });
            } else if (chunk.type === 'tool_call') {
              addMessage({
                role: 'tool',
                content: chunk.content,
                timestamp: new Date().toISOString()
              });
            }
          }
        }
      }
    } catch (error) {
      addMessage({
        role: 'error',
        content: `Error: ${error.message}`,
        timestamp: new Date().toISOString()
      });
    }
  };

  return (
    <div className="flex h-screen bg-white">
      <Sidebar 
        sessions={sessions}
        activeSession={sessionId}
        onSelectSession={setSessionId}
        onNewChat={createNewSession}
      />
      <div className="flex-1 flex flex-col">
        <MessageList messages={messages} />
        <ChatInput 
          onSend={handleSendMessage}
          disabled={loading}
        />
      </div>
    </div>
  );
}
```

**2.3 Create supporting components**

```jsx
// frontend/static/components/MessageList.jsx
import React, { useEffect, useRef } from 'react';
import { Message } from './Message';

export function MessageList({ messages }) {
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="flex-1 overflow-y-auto p-4 bg-gray-50">
      <div className="max-w-3xl mx-auto space-y-4">
        {messages.length === 0 ? (
          <div className="text-center text-gray-400 mt-8">
            <p className="text-lg">Start a conversation</p>
            <p className="text-sm">Ask me anything about patients, admissions, or your schedule</p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <Message key={idx} message={msg} />
          ))
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}

// frontend/static/components/ChatInput.jsx
import React, { useState } from 'react';

export function ChatInput({ onSend, disabled }) {
  const [input, setInput] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim()) {
      onSend(input);
      setInput('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="border-t p-4 bg-white">
      <div className="max-w-3xl mx-auto flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={disabled}
          placeholder="Ask about patients, schedules, or records..."
          className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          type="submit"
          disabled={disabled || !input.trim()}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </form>
  );
}

// frontend/static/components/Message.jsx
import React from 'react';
import MarkdownIt from 'markdown-it';

const md = new MarkdownIt();

export function Message({ message }) {
  const isUser = message.role === 'user';
  const isError = message.role === 'error';
  const isTool = message.role === 'tool';

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-md px-4 py-2 rounded-lg ${
          isUser
            ? 'bg-blue-600 text-white'
            : isError
            ? 'bg-red-100 text-red-800'
            : isTool
            ? 'bg-gray-200 text-gray-800'
            : 'bg-gray-200 text-gray-800'
        }`}
      >
        {isTool ? (
          <div className="text-sm">
            <strong>Tool Call:</strong>
            <pre className="bg-gray-100 p-2 mt-1 text-xs overflow-auto">
              {JSON.stringify(message.content, null, 2)}
            </pre>
          </div>
        ) : (
          <div
            className="text-sm"
            dangerouslySetInnerHTML={{
              __html: md.render(message.content)
            }}
          />
        )}
      </div>
    </div>
  );
}

// frontend/static/components/Sidebar.jsx
import React from 'react';

export function Sidebar({ sessions, activeSession, onSelectSession, onNewChat }) {
  return (
    <div className="w-64 bg-slate-900 text-white flex flex-col border-r">
      <div className="p-4 border-b">
        <button
          onClick={onNewChat}
          className="w-full px-4 py-2 bg-blue-600 rounded-lg hover:bg-blue-700 text-center"
        >
          + New Chat
        </button>
      </div>
      <div className="flex-1 overflow-y-auto">
        {sessions.map(session => (
          <button
            key={session.id}
            onClick={() => onSelectSession(session.id)}
            className={`w-full text-left px-4 py-3 text-sm border-b ${
              activeSession === session.id
                ? 'bg-blue-600 text-white'
                : 'hover:bg-slate-800'
            }`}
          >
            <div className="truncate font-medium">{session.title}</div>
            <div className="text-xs text-gray-400">
              {new Date(session.updated_at).toLocaleDateString()}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// frontend/static/hooks/useChat.js
import { useState, useCallback } from 'react';

export function useChat(sessionId) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);

  const addMessage = useCallback((message) => {
    setMessages(prev => [...prev, message]);
  }, []);

  return {
    messages,
    addMessage,
    loading,
    setLoading
  };
}
```

---

### Phase 3: Integration & Deployment (Week 3)

**3.1 Update Django Settings**

```python
# secure_hospital_ai/settings.py - Add:

# LLM Configuration
LLM_PROVIDER = env.str("LLM_PROVIDER", "openai")  # openai, anthropic, etc
LLM_MODEL = env.str("LLM_MODEL", "gpt-4-turbo-preview")
LLM_API_KEY = env.str("LLM_API_KEY", "")
LLM_TEMPERATURE = env.float("LLM_TEMPERATURE", 0.7)
LLM_MAX_TOKENS = env.int("LLM_MAX_TOKENS", 2000)
LLM_TIMEOUT = env.int("LLM_TIMEOUT", 30)

# Chat Configuration
CHAT_MAX_HISTORY = env.int("CHAT_MAX_HISTORY", 20)
CHAT_SESSION_TIMEOUT = env.int("CHAT_SESSION_TIMEOUT", 3600)  # 1 hour

# Update INSTALLED_APPS to register new models
INSTALLED_APPS = [
    # ... existing apps ...
    'frontend',  # Make sure this includes chat_handler models
]

# Add to DATABASES for chat
DATABASES = {
    'default': {
        # Your existing database config
    }
}
```

**3.2 Create migrations for Chat models**

```bash
python manage.py makemigrations frontend
python manage.py migrate
```

**3.3 Update URLs**

```python
# secure_hospital_ai/urls.py
from django.urls import path, include

urlpatterns = [
    path('api/chat/', include([
        path('message', views.chat_message, name='chat_message'),
        path('session', views.create_chat_session, name='create_session'),
        path('sessions', views.list_chat_sessions, name='list_sessions'),
        path('history/<str:session_id>', views.get_chat_history, name='chat_history'),
    ])),
    # ... existing patterns ...
]
```

---

## Best Practices & Security Checklist

### Before Going Live:

- ✅ **Rate Limiting**: Add rate limits on `/api/chat/message` to prevent token abuse
  ```python
  from django_ratelimit.decorators import ratelimit
  
  @ratelimit(key='user', rate='100/h', method='POST')
  @api_view(['POST'])
  def chat_message(request):
      # ...
  ```

- ✅ **Token Usage Tracking**: Store LLM API costs per user/session
  ```python
  class TokenUsageLog(models.Model):
      session = ForeignKey(ChatSession, ...)
      prompt_tokens = IntegerField()
      completion_tokens = IntegerField()
      total_tokens = IntegerField()
      estimated_cost = DecimalField()
  ```

- ✅ **Prompt Injection Prevention**: Sanitize user inputs before sending to LLM
  ```python
  def sanitize_prompt(text):
      # Remove SQL injection attempts
      # Remove jailbreak patterns
      # Limit length
      return text[:5000]
  ```

- ✅ **Tool Validation**: Validate tool calls before executing
  ```python
  def validate_tool_call(tool_name, arguments):
      allowed_tools = ["get_patient_overview", ...]
      if tool_name not in allowed_tools:
          raise ToolNotAllowed(f"{tool_name} not available for {user.role}")
  ```

- ✅ **Error Handling**: Never expose internal errors to LLM
  ```python
  try:
      result = mcp_proxy(...)
  except DatabaseError as e:
      logger.error(e)  # Log internally
      return {"error": "Data unavailable"}  # Generic to LLM
  ```

- ✅ **Audit Logging**: Every LLM interaction logged
  ```python
  AuditLog.objects.create(
      user=user,
      action="LLM_CALL",
      table_name="LLM",
      is_phi_access=True,  # Mark if PHI was accessed
      ip_address=ip
  )
  ```

---

## Environment Variables (.env)

```bash
# LLM Configuration
LLM_PROVIDER=openai
LLM_MODEL=gpt-4-turbo-preview
LLM_API_KEY=sk-...your-key...
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2000

# Frontend
REACT_APP_API_URL=http://localhost:8000/api
REACT_APP_WS_URL=ws://localhost:8000/ws
```

---

## Recommended LLM Providers & Pricing

| Provider | Model | Cost | Recommendation |
|----------|-------|------|---|
| **OpenAI** | gpt-4-turbo | $0.01-0.03/1K tokens | Best for general tasks, HIPAA BAA available |
| **Anthropic** | Claude 3 | $0.003-0.03/1K tokens | Better context window, fewer jailbreaks |
| **Azure OpenAI** | gpt-4, gpt-3.5 | $0.01-0.03/1K tokens | Enterprise, HIPAA compliance, managed by Azure |
| **Self-Hosted** | Llama 2, Mistral | Free | Maximum control, no data leakage, slower |

**Recommendation for Healthcare**: Use **Azure OpenAI** or **Anthropic Claude** with BAA (Business Associate Agreement) for HIPAA compliance.

---

## Testing Strategy

**Unit Tests** (`tests.py`):
```python
def test_llm_handler_role_based_tools(self):
    """Doctor should not get billing tools"""
    doctor = User.objects.create(username="doc", role="Doctor")
    handler = LLMAgentHandler(doctor)
    tools = handler._get_available_tools()
    tool_names = [t['function']['name'] for t in tools]
    self.assertNotIn("billing_access", tool_names)

def test_chat_session_isolation(self):
    """Users cannot access each other's chats"""
    user1 = User.objects.create(username="user1")
    user2 = User.objects.create(username="user2")
    session1 = ChatSession.objects.create(user=user1, title="Private")
    
    with self.assertRaises(ChatSession.DoesNotExist):
        ChatContextManager.get_session(user2, session1.id)
```

**Integration Tests**:
```bash
# Test streaming response
curl -X POST http://localhost:8000/api/chat/message \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "uuid", "message": "Get patient PAT-001"}' \
  --no-buffer
```

---

## Performance & Scaling

1. **Cache LLM responses** for common queries
   ```python
   from django.views.decorators.cache import cache_page
   
   RESPONSE_CACHE_TIMEOUT = 3600  # 1 hour
   ```

2. **Queue LLM tasks** for heavy operations
   ```python
   # Use Celery for async LLM calls
   @shared_task
   def call_llm_async(user_id, session_id, message):
       # ...
   ```

3. **Monitor token usage** to catch runaway costs
   ```python
   if total_tokens > DAILY_LIMIT:
       raise TokenLimitExceeded()
   ```

---

## Conclusion

Your backend MCP and RBAC are solid. Now you need:

1. **LLM Handler** (Python) – Manage prompts, tools, streaming
2. **Chat API** (Django) – Session management, history
3. **React Frontend** – Beautiful chat UI with streaming support
4. **Monitoring** – Token costs, error tracking, audit logging

This will give you a production-ready AI-augmented hospital system that maintains HIPAA compliance while enabling powerful AI-assisted workflows.

Start with Phase 1 (backend), then Phase 2 (frontend), then Phase 3 (integration). This ensures your security layer is solid before adding the UX layer.

---

*Questions? Review the `mcp_server/main.py` for the MCP tool definitions and mirror them in `llm_handler.py` for consistency.*
