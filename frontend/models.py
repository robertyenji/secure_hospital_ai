"""
Frontend Chat Models – LLM Chatbot Integration
-----------------------------------------------
Stores conversation history for hospital staff interacting with LLM agent.
- ChatSession: Individual conversation container (per user per date)
- ChatMessage: Individual messages in conversation (user input + AI response)

Notes:
- All timestamps auto-captured
- User FK for RBAC enforcement
- role_at_message_time: Captures user's role at time of message (for audit/compliance)
"""

from django.db import models
from django.conf import settings
import json


class ChatSession(models.Model):
    """
    Represents a single conversation session between a user and the LLM agent.
    
    RBAC:
    - Users can only view/edit their own sessions
    - Admins can view all sessions
    - Auditors can view all sessions (read-only)
    """
    
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_sessions')
    
    # Session metadata
    title = models.CharField(max_length=255, default="New Chat")  # User can rename conversation
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Summary of conversation (for quick preview)
    summary = models.TextField(blank=True, default="")
    
    # Session context (stored as JSON for flexibility)
    # Can include: patient_id, department, context flags, etc.
    context = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Chat Session"
        verbose_name_plural = "Chat Sessions"
    
    def __str__(self):
        return f"{self.user.username} - {self.title} ({self.created_at.strftime('%Y-%m-%d')})"


class ChatMessage(models.Model):
    """
    Represents a single message in a chat session.
    Supports streaming content and usage tracking.
    
    RBAC:
    - Messages only visible to owner, admins, and auditors
    - Streaming responses are NDJSON (handled via streaming view)
    """
    
    ROLE_CHOICES = [
        ('user', 'User Message'),
        ('assistant', 'LLM Assistant'),
        ('system', 'System Message'),
    ]
    
    id = models.BigAutoField(primary_key=True)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    
    # Message content
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    
    # Timestamp and tracking
    created_at = models.DateTimeField(auto_now_add=True)
    user_role_at_time = models.CharField(max_length=20, blank=True)  # For audit: what role when sent
    
    # Streaming support: true if this was a streamed response
    is_streamed = models.BooleanField(default=False)
    
    # LLM metadata
    model_used = models.CharField(max_length=100, blank=True, default="")  # e.g., "gpt-4-turbo"
    tokens_used = models.IntegerField(null=True, blank=True)  # Input + output tokens
    cost_cents = models.IntegerField(null=True, blank=True)   # Cost in cents ($0.01 = 1)
    
    # Tool calls from this message (stored as JSON array)
    # Example: [{"tool": "get_patient_data", "patient_id": "abc123", "result": {...}}]
    tool_calls = models.JSONField(default=list, blank=True)
    
    class Meta:
        ordering = ["created_at"]
        verbose_name = "Chat Message"
        verbose_name_plural = "Chat Messages"
        indexes = [
            models.Index(fields=['session', 'created_at']),
            models.Index(fields=['session', 'role']),
        ]
    
    def __str__(self):
        preview = self.content[:50].replace('\n', ' ')
        return f"{self.role.upper()} - {preview}..."
