# frontend/llm_handler.py
"""
LLM Handler with:
- RBAC enforcement
- MCP multi-tool support with OpenAI function calling
- Safe synchronous wrapper for async OpenAI calls
- Streaming + non-streaming modes
- Conversation history loading (FIXED for async context)
"""

import os
import json
import asyncio
import requests
from uuid import uuid4
from django.conf import settings
from asgiref.sync import sync_to_async  # CRITICAL: Import for Django ORM in async

from audit.models import AuditLog
from frontend.models import ChatMessage, ChatSession


# ============================================================
# CONFIG
# ============================================================

class LLMConfig:
    MODEL = "gpt-4o-mini"
    MCP_URL = "http://127.0.0.1:9000/mcp/"
    OPENAI_KEY = (
        getattr(settings, 'OPENAI_API_KEY', None) or
        os.getenv('OPENAI_API_KEY') or
        os.getenv('OPENAI_KEY') or
        os.getenv('LLM_API_KEY')
    )
    
    if not OPENAI_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured! Set it in .env file.")


# ============================================================
# MCP TOOL DEFINITIONS FOR OPENAI
# ============================================================

MCP_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_patient_overview",
            "description": "Get basic patient information including name, DOB year, gender. This is non-PHI data accessible to most roles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "The patient ID (e.g., 'FCE57')"
                    }
                },
                "required": ["patient_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_patient_phi",
            "description": "Get Protected Health Information (PHI) including SSN, full DOB, address, phone, email, insurance. REQUIRES: Admin, Doctor, Nurse, Auditor, or Billing role. Billing role receives ONLY insurance information (provider and policy number). Use this when user asks for sensitive info like SSN, address, insurance details.",
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
            "name": "get_medical_records",
            "description": "Get detailed medical records including diagnoses, treatments, and visit history. REQUIRES: Doctor, Nurse, Admin, or Auditor role.",
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
            "name": "get_appointments",
            "description": "Get appointment history for a patient including dates, status, and assigned staff.",
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
            "name": "get_admissions",
            "description": "Get hospital admission records for a patient including room numbers and dates.",
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
            "description": "Get YOUR OWN shift schedule. Use this when the user asks about 'my shifts', 'my schedule', etc. No parameters needed - automatically uses current user's staff ID.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_shifts",
            "description": "Get shift schedule for a SPECIFIC staff member by their staff_id. Use only when asked about someone else's schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "staff_id": {
                        "type": "string",
                        "description": "The staff member ID"
                    }
                },
                "required": ["staff_id"]
            }
        }
    }
]


# ============================================================
# UTILS
# ============================================================

def sync_await(coro):
    """Synchronously run an async coroutine safely."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        new_loop = asyncio.new_event_loop()
        return new_loop.run_until_complete(coro)
    else:
        return loop.run_until_complete(coro)


def safe_json(obj):
    """Prevents UUID serialization errors."""
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return json.dumps({"error": "serialization_failed"})


# ============================================================
# RBAC ENFORCEMENT
# ============================================================

def rbac_filter_text(role, text):
    """Extra UI-layer protection for PHI."""
    if role in ["Admin", "Auditor", "Doctor", "Nurse"]:
        return text

    if "HIV" in text:
        text = text.replace("HIV", "[REDACTED]")
    if "SSN" in text:
        text = text.replace("SSN", "[REDACTED]")

    return text


# ============================================================
# MCP TOOL CALLER (FIXED NULL HANDLING)
# ============================================================

def call_mcp_tool(tool_name, arguments, jwt_token):
    """
    Sends JSON-RPC call to MCP server.
    Returns dict: {"success", "data", "error"}
    """
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": "tools.call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }

    print(f"📤 Calling MCP tool: {tool_name} with args: {arguments}")

    try:
        resp = requests.post(
            LLMConfig.MCP_URL,
            json=payload,
            headers={"Authorization": f"Bearer {jwt_token}"},
            timeout=25
        )
        print(f"📥 MCP Response status: {resp.status_code}")
    except Exception as e:
        print(f"❌ MCP connection error: {e}")
        return {"success": False, "error": f"MCP unreachable: {e}"}

    if resp.status_code == 422:
        print(f"❌ MCP 422 Error - Payload validation failed")
        print(f"   Sent payload: {payload}")
        print(f"   Response: {resp.text}")
        return {"success": False, "error": f"MCP validation error: {resp.text}"}

    # FIX: Handle null/empty responses
    try:
        j = resp.json()
        print(f"📥 MCP Response: {j}")
    except Exception:
        print(f"❌ Failed to parse MCP response: {resp.text}")
        return {"success": False, "error": f"Bad MCP response: {resp.text}"}

    # FIX: Null check
    if j is None:
        print(f"❌ MCP returned null for tool: {tool_name}")
        return {"success": False, "error": f"Tool '{tool_name}' not implemented in MCP server"}

    if not isinstance(j, dict):
        return {"success": False, "error": f"Unexpected response type: {type(j).__name__}"}

    if "result" in j:
        result = j["result"]
        
        # Handle error in result
        if isinstance(result, dict) and result.get("error"):
            return {"success": False, "error": result.get("error")}
        
        data = result.get("data") if isinstance(result, dict) else result
        
        # Empty data is still a success (just no records)
        print(f"✅ MCP Success - returned {len(data) if isinstance(data, list) else 'data'}")
        return {"success": True, "data": data}
    
    elif "error" in j:
        error = j.get("error", {})
        error_msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        print(f"❌ MCP Error: {error_msg}")
        return {"success": False, "error": error_msg}
    
    else:
        return {"success": False, "error": "Unexpected MCP response structure"}


# ============================================================
# STREAMING LLM HANDLER WITH MCP TOOLS (FIXED ASYNC)
# ============================================================

class StreamingLLMAgent:
    """
    Provides async token stream via OpenAI with MCP tool calling.
    Yields JSON dicts:
      {"type": "message", "content": "..."}  
      {"type": "tool_call", "tool_name": ..., "arguments": ...}
      {"type": "tool_result", "tool_name": ..., "data": ...}
    """

    def __init__(self, user, request, session=None):
        self.user = user
        self.request = request
        self.session = session  # ChatSession object
        self.jwt = request.session.get("access_jwt")
        
        # Initialize context
        self.conversation_context = {
            "last_patient_id": None,
            "last_patient_name": None,
            "recent_tool_data": {}
        }

    async def _load_context_from_session(self):
        """Load persisted context from session (async-safe)."""
        if not self.session:
            return
        
        # Use sync_to_async for Django ORM access
        @sync_to_async
        def get_context():
            # Refresh from database
            self.session.refresh_from_db()
            return self.session.context or {}
        
        try:
            context = await get_context()
            self.conversation_context["last_patient_id"] = context.get("last_patient_id")
            self.conversation_context["last_patient_name"] = context.get("last_patient_name")
            print(f"🧠 Loaded context: patient={self.conversation_context['last_patient_id']}")
        except Exception as e:
            print(f"⚠️ Could not load context: {e}")

    async def _save_context_to_session(self):
        """Persist conversation context to database (async-safe)."""
        if not self.session:
            return
        
        @sync_to_async
        def save_context():
            self.session.context = {
                "last_patient_id": self.conversation_context.get("last_patient_id"),
                "last_patient_name": self.conversation_context.get("last_patient_name"),
            }
            self.session.save(update_fields=["context"])
        
        try:
            await save_context()
            print(f"💾 Saved context: patient={self.conversation_context['last_patient_id']}")
        except Exception as e:
            print(f"⚠️ Could not save context: {e}")

    async def _load_conversation_history(self, limit=10):
        """Load recent messages from this session for context (async-safe)."""
        if not self.session:
            return []
        
        @sync_to_async
        def get_messages():
            messages = list(
                ChatMessage.objects.filter(session=self.session)
                .order_by("-created_at")[:limit]
            )
            # Reverse to chronological order
            return list(reversed(messages))
        
        try:
            messages = await get_messages()
            
            # Convert to OpenAI format
            history = []
            for msg in messages:
                if msg.role in ["user", "assistant"]:
                    history.append({
                        "role": msg.role,
                        "content": msg.content
                    })
            
            return history
        except Exception as e:
            print(f"⚠️ Could not load history: {e}")
            return []

    async def stream_chat(self, user_message):
        """
        Async generator that yields token or event chunks.
        Handles multi-turn tool calling loop.
        """
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(api_key=LLMConfig.OPENAI_KEY)

        # Load context from session (async-safe)
        await self._load_context_from_session()

        # Get user context
        role = getattr(self.user, 'role', 'Unknown')
        username = getattr(self.user, 'username', 'Unknown')
        user_id = str(self.user.id)
        
        # Try to get staff_id and staff details
        staff_id = None
        staff_name = None
        staff_type = None
        department = None
        
        try:
            @sync_to_async
            def get_staff_info():
                from ehr.models import Staff
                staff = Staff.objects.filter(user=self.user).first()
                if staff:
                    return {
                        "staff_id": str(staff.staff_id),
                        "staff_name": staff.full_name,
                        "staff_type": staff.staff_type,
                        "department": staff.department or "Not assigned"
                    }
                return None
            
            staff_info = await get_staff_info()
            if staff_info:
                staff_id = staff_info["staff_id"]
                staff_name = staff_info["staff_name"]
                staff_type = staff_info["staff_type"]
                department = staff_info["department"]
        except Exception as e:
            print(f"Warning: Could not fetch staff details: {e}")

        # Build context info from persisted state
        context_info = ""
        if self.conversation_context.get("last_patient_id"):
            pid = self.conversation_context['last_patient_id']
            pname = self.conversation_context.get('last_patient_name', 'Unknown')
            context_info = f"""

CURRENT CONVERSATION CONTEXT:
- Last discussed patient: {pname} (ID: {pid})
- When user says 'his/her/their', 'the patient', 'them', they mean patient {pid}
- When user asks "when was the patient admitted" or "their appointments" without specifying ID, use {pid}
- IMPORTANT: Use patient ID {pid} for follow-up questions about this patient"""

        system_prompt = f"""You are SecureHospital AI Assistant, a professional medical information system for hospital staff.

CURRENT USER:
- Username: {username}
- Role: {role}
- Staff ID: {staff_id or 'Not linked to staff record'}
- Staff Name: {staff_name or 'N/A'}
- Department: {department or 'N/A'}
{context_info}

IMPORTANT: When user asks "my schedule", "my shifts", or refers to "me/my", use get_my_shifts tool.

AVAILABLE TOOLS & RBAC RULES:
1. get_patient_overview: Basic patient info (name, birth year, gender) - Available to ALL roles
2. get_patient_phi: Protected Health Information including SSN, full DOB, address, insurance
   - Full Access: Admin, Doctor, Auditor (all PHI fields)
   - Redacted Access: Nurse (SSN/address hidden)
   - Insurance Only: Billing (only insurance_provider and insurance_number)
   - Denied: Reception (no access)
   - USE THIS when asked for SSN, address, phone, email, insurance
3. get_medical_records: Clinical records with diagnoses and treatments
   - Available to: Admin, Doctor, Nurse, Auditor
4. get_appointments: Patient appointment history - Available to ALL roles
5. get_admissions: Hospital admission records - Available to ALL roles
6. get_my_shifts: YOUR shift schedule (uses your staff ID automatically)
   - Use when user asks: "my shifts", "my schedule", "when do I work"
7. get_shifts: Specific staff member's schedule (requires staff_id parameter)
   - Use when asked about someone else's schedule

CRITICAL - HANDLING TOOL RESULTS:
- If tool returns EMPTY data (empty list or null), tell user "No [records/appointments/admissions] found for this patient"
- If tool returns ERROR, tell user "Unable to retrieve data due to: [specific reason]"
- NEVER say "unable to retrieve" when data simply doesn't exist - be specific!
- Example: "Patient FCE57 has no hospital admissions on record" is CORRECT
- Example: "I cannot retrieve admission records" is WRONG when patient just has no admissions

CONTEXT INTELLIGENCE:
- Remember which patient we're discussing throughout the conversation
- "his/her/their" or "the patient" refers to the last mentioned patient
- "when was the patient admitted" → use the patient we've been discussing
- If no patient context exists, ask user to specify patient ID

RESPONSE FORMAT - USE MARKDOWN:
- Use ### for headings
- Use **bold** for labels and important info
- Use - for bullet lists
- Use numbered lists 1. 2. for sequences
- Add emojis for visual appeal: 🔴 (urgent), ⏰ (time), ✅ (complete), 📋 (record)
- Keep responses clean and scannable

Your role ({role}) permissions:
- Admin: Full access to everything
- Doctor: Full clinical access + PHI
- Nurse: Full clinical access + PHI
- Auditor: Read-only access to ALL data including PHI (for compliance)
- Billing: Patient demographics + insurance only (no medical records)
- Reception: Basic patient info + appointments only"""

        # Load conversation history (async-safe)
        history = await self._load_conversation_history(limit=8)
        print(f"📜 Loaded {len(history)} messages from history")

        # Build messages array with history
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)  # Add previous messages
        messages.append({"role": "user", "content": user_message})

        # Multi-turn loop for tool calling
        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            try:
                # Stream from OpenAI with tools
                stream = await client.chat.completions.create(
                    model=LLMConfig.MODEL,
                    messages=messages,
                    tools=MCP_TOOLS,
                    tool_choice="auto",
                    stream=True
                )

                current_tool_call = None
                accumulated_arguments = ""
                accumulated_content = ""

                async for chunk in stream:
                    if not chunk.choices:
                        continue
                    
                    choice = chunk.choices[0]
                    delta = choice.delta

                    # Regular message content
                    if delta.content:
                        accumulated_content += delta.content
                        yield safe_json({
                            "type": "message",
                            "content": delta.content
                        })

                    # Tool call started
                    if delta.tool_calls:
                        for tool_call_delta in delta.tool_calls:
                            if tool_call_delta.function:
                                if tool_call_delta.function.name:
                                    current_tool_call = {
                                        "id": tool_call_delta.id,
                                        "name": tool_call_delta.function.name
                                    }
                                    accumulated_arguments = ""
                                
                                if tool_call_delta.function.arguments:
                                    accumulated_arguments += tool_call_delta.function.arguments

                    # Stream finished
                    if choice.finish_reason:
                        if choice.finish_reason == "tool_calls" and current_tool_call:
                            # Parse arguments and call MCP tool
                            try:
                                arguments = json.loads(accumulated_arguments)
                            except:
                                arguments = {}

                            tool_name = current_tool_call["name"]
                            
                            yield safe_json({
                                "type": "tool_call",
                                "tool_name": tool_name,
                                "arguments": arguments
                            })

                            # Call MCP
                            mcp_result = call_mcp_tool(tool_name, arguments, self.jwt)

                            # Update context based on tool results
                            if tool_name == "get_patient_overview" and mcp_result.get("success"):
                                data = mcp_result.get("data")
                                if data:
                                    self.conversation_context["last_patient_id"] = data.get("patient_id")
                                    first = data.get("first_name", "")
                                    last = data.get("last_name", "")
                                    self.conversation_context["last_patient_name"] = f"{first} {last}".strip()
                                    await self._save_context_to_session()
                                    print(f"🧠 MEMORY: Stored patient {self.conversation_context['last_patient_id']}")
                            
                            elif tool_name == "get_patient_phi" and mcp_result.get("success"):
                                data = mcp_result.get("data")
                                if data and data.get("patient_id"):
                                    self.conversation_context["last_patient_id"] = data.get("patient_id")
                                    await self._save_context_to_session()
                                    print(f"🧠 MEMORY: Updated patient context to {data.get('patient_id')}")
                            
                            elif tool_name == "get_medical_records" and mcp_result.get("success"):
                                data = mcp_result.get("data")
                                if data and len(data) > 0 and data[0].get("patient_id"):
                                    self.conversation_context["last_patient_id"] = data[0].get("patient_id")
                                    await self._save_context_to_session()
                                    print(f"🧠 MEMORY: Updated patient context to {data[0].get('patient_id')}")
                            
                            elif tool_name == "get_appointments" and mcp_result.get("success"):
                                data = mcp_result.get("data")
                                if data and len(data) > 0 and data[0].get("patient_id"):
                                    self.conversation_context["last_patient_id"] = data[0].get("patient_id")
                                    await self._save_context_to_session()
                                    print(f"🧠 MEMORY: Updated patient context to {data[0].get('patient_id')}")
                            
                            elif tool_name == "get_admissions" and mcp_result.get("success"):
                                data = mcp_result.get("data")
                                if data and len(data) > 0 and data[0].get("patient_id"):
                                    self.conversation_context["last_patient_id"] = data[0].get("patient_id")
                                    await self._save_context_to_session()

                            # Store recent tool data for quick reference
                            self.conversation_context["recent_tool_data"][tool_name] = mcp_result.get("data")

                            # Check if result is empty (not an error, just no data)
                            result_data = mcp_result.get("data")
                            is_empty = (
                                result_data is None or 
                                (isinstance(result_data, list) and len(result_data) == 0)
                            )

                            yield safe_json({
                                "type": "tool_result",
                                "tool_name": tool_name,
                                "success": mcp_result["success"],
                                "data": mcp_result.get("data"),
                                "error": mcp_result.get("error"),
                                "is_empty": is_empty
                            })

                            # Add tool call and result to conversation
                            messages.append({
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [{
                                    "id": current_tool_call["id"],
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": accumulated_arguments
                                    }
                                }]
                            })

                            # Build tool response with hint about empty data
                            if is_empty and mcp_result["success"]:
                                tool_response = {
                                    "_note": f"No {tool_name.replace('get_', '').replace('_', ' ')} found - this is NOT an error, the patient simply has no data of this type. Tell the user clearly that no records were found.",
                                    "data": []
                                }
                            else:
                                tool_response = mcp_result.get("data") or {"error": mcp_result.get("error")}

                            messages.append({
                                "role": "tool",
                                "tool_call_id": current_tool_call["id"],
                                "content": json.dumps(tool_response)
                            })

                            # Continue loop to get final response
                            break

                        elif choice.finish_reason == "stop":
                            # Conversation complete
                            return

                        else:
                            # Other finish reasons
                            return

                else:
                    # If we didn't break (no tool calls), exit loop
                    return

            except Exception as e:
                print(f"OpenAI API Error: {e}")
                yield safe_json({"type": "error", "content": str(e)})
                return


# ============================================================
# NON-STREAMING LLM HANDLER (for classic chat)
# ============================================================

class LLMAgentHandler:
    def __init__(self, user, request=None):
        self.user = user
        self.request = request
        self.jwt = request.session.get("access_jwt") if request else None

    def get_response(self, user_message):
        """Non-streaming version - returns complete response."""
        from openai import OpenAI
        client = OpenAI(api_key=LLMConfig.OPENAI_KEY)

        role = getattr(self.user, 'role', 'Unknown')
        system_prompt = f"""You are SecureHospital AI Assistant.
User role: {role}
User: {self.user.username}

Use available tools to answer questions about patients, appointments, and medical records.
Always respect RBAC - if data is redacted or missing, explain access limitations."""

        try:
            response = client.chat.completions.create(
                model=LLMConfig.MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                tools=MCP_TOOLS,
                tool_choice="auto"
            )

            message = response.choices[0].message

            # Handle tool calls
            if message.tool_calls:
                # Process all tool calls
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    
                    # Call MCP
                    mcp_result = call_mcp_tool(tool_name, arguments, self.jwt)

                # Get final response after tool calls
                content = f"Tool data retrieved. Please ask your question again for analysis."
            else:
                content = message.content

            # Apply RBAC filtering
            content = rbac_filter_text(role, content)

            return {
                "content": content,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "tool_calls": message.tool_calls if message.tool_calls else []
            }

        except Exception as e:
            return {"error": str(e)}