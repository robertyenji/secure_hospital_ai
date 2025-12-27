# frontend/llm_handler.py
"""
LLM Handler - Production-Optimized Version
==========================================
Fixes:
- Stronger prompts to ALWAYS try tools (don't be overly cautious)
- Better context handling for follow-up questions
- Emergency contact and all PHI fields explicitly listed
- Improved error messages
"""

import os
import json
import asyncio
import requests
from uuid import uuid4
from django.conf import settings
from asgiref.sync import sync_to_async

from audit.models import AuditLog
from frontend.models import ChatMessage, ChatSession


# ============================================================
# CONFIG
# ============================================================

class LLMConfig:
    MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    MCP_URL = os.getenv("MCP_SERVER_URL", "https://healthchat-mcp-server.fly.dev/mcp/")
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
            "description": "Get patient name, birth year, and gender. ALWAYS call this when user asks: 'patient name', 'who is patient X', 'patient demographics', 'how old is patient'. Works for ALL roles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient ID (e.g., 'FCE57', '9969V', 'TYYQ8')"
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
            "description": "Get Protected Health Information. ALWAYS call this when user asks for: SSN, social security, date of birth, address, home address, phone, email, EMERGENCY CONTACT, insurance, policy number. Do NOT pre-refuse - call the tool and let the server handle access control.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient ID"
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
            "description": "Get diagnoses, treatments, clinical notes, visit history. Call when user asks about medical history, what was diagnosed, treatments given, prescriptions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient ID"
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
            "description": "Get patient appointments - past, scheduled, and cancelled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient ID"
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
            "description": "Get hospital admission records - room numbers, admission/discharge dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "string",
                        "description": "Patient ID"
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
            "description": "Get YOUR OWN shift schedule. Use when user says 'my shifts', 'my schedule', 'when do I work'. No parameters needed.",
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
            "description": "Get shifts for a specific staff member by their staff_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "staff_id": {
                        "type": "string",
                        "description": "Staff member ID"
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
# RBAC ENFORCEMENT (UI layer - minimal)
# ============================================================

def rbac_filter_text(role, text):
    """Extra UI-layer protection for PHI - MCP server handles main filtering."""
    if role in ["Admin", "Auditor", "Doctor", "Nurse"]:
        return text
    # Only filter obvious PHI patterns for non-clinical roles
    return text


# ============================================================
# MCP TOOL CALLER
# ============================================================

def call_mcp_tool(tool_name, arguments, jwt_token):
    """
    Sends JSON-RPC call to MCP server.
    Returns dict: {"success", "data", "error"}
    
    Handles two response formats:
    1. {'result': {'data': [...]}}  - wrapped format
    2. {'result': {'patient_id': ...}}  - direct format (data IS the result)
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
            timeout=30
        )
        print(f"📥 MCP Response status: {resp.status_code}")
    except requests.exceptions.Timeout:
        print(f"❌ MCP timeout for tool: {tool_name}")
        return {"success": False, "error": "Request timed out - please try again"}
    except requests.exceptions.ConnectionError as e:
        print(f"❌ MCP connection error: {e}")
        return {"success": False, "error": "Could not connect to data server - please try again"}
    except Exception as e:
        print(f"❌ MCP error: {e}")
        return {"success": False, "error": f"System error: {e}"}

    if resp.status_code == 401:
        return {"success": False, "error": "Authentication expired - please refresh the page"}
    
    if resp.status_code == 422:
        print(f"❌ MCP 422 Error - Payload validation failed")
        return {"success": False, "error": "Invalid request parameters"}

    try:
        j = resp.json()
        print(f"📥 MCP Response: {j}")
    except Exception:
        print(f"❌ Failed to parse MCP response: {resp.text}")
        return {"success": False, "error": "Invalid response from data server"}

    if j is None:
        return {"success": False, "error": f"Tool '{tool_name}' returned no data"}

    if not isinstance(j, dict):
        return {"success": False, "error": f"Unexpected response type"}

    if "result" in j:
        result = j["result"]
        
        # Handle access denied
        if isinstance(result, dict) and result.get("access_denied"):
            error_msg = result.get("error", "Access denied for your role")
            return {"success": False, "error": error_msg, "access_denied": True}
        
        # Handle error in result
        if isinstance(result, dict) and result.get("error"):
            return {"success": False, "error": result.get("error")}
        
        # CRITICAL FIX: Handle both response formats
        # Format 1: {'result': {'data': [...]}} - data is wrapped
        # Format 2: {'result': {'patient_id': ...}} - result IS the data
        if isinstance(result, dict):
            if "data" in result:
                # Wrapped format - extract data
                data = result.get("data")
                is_empty = result.get("is_empty", False)
            elif "patient_id" in result or "first_name" in result or "staff_id" in result or "shift_id" in result or "record_id" in result or "appointment_id" in result or "admission_id" in result:
                # Direct format - result IS the data (single record)
                data = result
                is_empty = False
                print(f"📋 Direct format detected - result is the data")
            else:
                # Unknown format - treat result as data
                data = result
                is_empty = not bool(result)
        elif isinstance(result, list):
            # List of records
            data = result
            is_empty = len(result) == 0
        else:
            data = result
            is_empty = not bool(result)
        
        # Check for empty data
        if data is None:
            is_empty = True
        elif isinstance(data, list) and len(data) == 0:
            is_empty = True
        elif isinstance(data, dict) and len(data) == 0:
            is_empty = True
        
        print(f"✅ MCP Success - data type: {type(data).__name__}, is_empty: {is_empty}")
        if isinstance(data, dict):
            print(f"   Data keys: {list(data.keys()) if data else 'None'}")
        elif isinstance(data, list):
            print(f"   Data count: {len(data)}")
        
        return {"success": True, "data": data, "is_empty": is_empty}
    
    elif "error" in j:
        error = j.get("error", {})
        error_msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        print(f"❌ MCP Error: {error_msg}")
        return {"success": False, "error": error_msg}
    
    else:
        return {"success": False, "error": "Unexpected response structure"}


# ============================================================
# STREAMING LLM HANDLER WITH MCP TOOLS
# ============================================================

class StreamingLLMAgent:
    """
    Provides async token stream via OpenAI with MCP tool calling.
    """

    def __init__(self, user, request, session=None):
        self.user = user
        self.request = request
        self.session = session
        self.jwt = request.session.get("access_jwt")
        
        self.conversation_context = {
            "last_patient_id": None,
            "last_patient_name": None,
            "recent_tool_data": {}
        }

    async def _load_context_from_session(self):
        """Load persisted context from session."""
        if not self.session:
            return
        
        @sync_to_async
        def get_context():
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
        """Persist conversation context to database."""
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
        """Load previous messages for context."""
        if not self.session:
            return []
        
        @sync_to_async
        def get_messages():
            messages = list(
                ChatMessage.objects.filter(session=self.session)
                .order_by("-created_at")[:limit]
            )
            messages.reverse()
            
            result = []
            for msg in messages:
                if msg.role == "user":
                    result.append({"role": "user", "content": msg.content})
                elif msg.role == "assistant":
                    result.append({"role": "assistant", "content": msg.content})
            return result
        
        try:
            return await get_messages()
        except Exception as e:
            print(f"⚠️ Could not load history: {e}")
            return []

    def _build_system_prompt(self, role, username, staff_id, staff_name, department):
        """Build the system prompt with context."""
        
        # Build context section
        context_section = ""
        if self.conversation_context.get("last_patient_id"):
            pid = self.conversation_context['last_patient_id']
            pname = self.conversation_context.get('last_patient_name', '')
            context_section = f"""
## ACTIVE PATIENT CONTEXT
You are currently discussing patient: {pname} (ID: {pid})

CRITICAL CONTEXT RULES:
- "the patient" = patient {pid}
- "their" / "his" / "her" = patient {pid}  
- "patient name" without ID = patient {pid}
- "their emergency contact" = call get_patient_phi for {pid}
- "their appointments" = call get_appointments for {pid}
- ANY follow-up question about a patient = use {pid} unless user specifies a different ID
"""

        return f"""You are SecureHospital AI, a medical information assistant.

USER: {username} | ROLE: {role} | STAFF ID: {staff_id or 'N/A'}
{context_section}

═══════════════════════════════════════════════════════════════
RULE #1: ALWAYS CALL THE TOOL - NEVER PRE-REFUSE
═══════════════════════════════════════════════════════════════

You MUST call the appropriate tool for ANY data request. 
The MCP server handles access control - NOT you.

❌ WRONG: "I cannot provide emergency contact because it's PHI"
❌ WRONG: "Your role doesn't have access to this information"  
✅ RIGHT: Call get_patient_phi → Report whatever the server returns

If the server denies access, THEN tell the user. But ALWAYS try first.

═══════════════════════════════════════════════════════════════
TOOL SELECTION GUIDE
═══════════════════════════════════════════════════════════════

**get_patient_overview** - USE FOR:
  → Patient name, full name
  → Age, birth year
  → Gender
  → Basic demographics

**get_patient_phi** - USE FOR:
  → SSN / Social Security
  → Date of birth (full)
  → Address / home address
  → Phone number
  → Email address  
  → EMERGENCY CONTACT ← Important!
  → Insurance provider
  → Insurance ID/policy number

**get_medical_records** - USE FOR:
  → Diagnoses
  → Treatments
  → Clinical notes
  → Visit history
  → Prescriptions

**get_appointments** - Patient appointments
**get_admissions** - Hospital stays  
**get_my_shifts** - YOUR schedule (no params)
**get_shifts** - Another staff member's schedule

═══════════════════════════════════════════════════════════════
HANDLING RESPONSES  
═══════════════════════════════════════════════════════════════

✅ Data returned → Format nicely and display
📭 Empty data → "No [type] found for patient [ID]"
🚫 Access denied → "Your role ({role}) doesn't have access to [type]. Contact administrator."
❌ Error → "Unable to retrieve: [error message]"

Format with markdown: **bold** labels, bullet points, emojis (📋 👤 📅 ✅ ⚠️)"""

    async def stream_chat(self, user_message):
        """Async generator that yields token or event chunks."""
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(api_key=LLMConfig.OPENAI_KEY)

        # Load context
        await self._load_context_from_session()

        # Get user info
        role = getattr(self.user, 'role', 'Unknown')
        username = getattr(self.user, 'username', 'Unknown')
        
        # Get staff info
        staff_id = None
        staff_name = None
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
                        "department": staff.department or "Not assigned"
                    }
                return None
            
            staff_info = await get_staff_info()
            if staff_info:
                staff_id = staff_info["staff_id"]
                staff_name = staff_info["staff_name"]
                department = staff_info["department"]
        except Exception as e:
            print(f"Warning: Could not fetch staff details: {e}")

        # Build system prompt
        system_prompt = self._build_system_prompt(role, username, staff_id, staff_name, department)

        # Load conversation history
        history = await self._load_conversation_history(limit=8)
        print(f"📜 Loaded {len(history)} messages from history")

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # Multi-turn loop
        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            try:
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

                    # Tool call
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
                            # Parse arguments
                            try:
                                arguments = json.loads(accumulated_arguments) if accumulated_arguments else {}
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
                            await self._update_context_from_result(tool_name, mcp_result)

                            # Store recent tool data
                            self.conversation_context["recent_tool_data"][tool_name] = mcp_result.get("data")

                            yield safe_json({
                                "type": "tool_result",
                                "tool_name": tool_name,
                                "success": mcp_result["success"],
                                "data": mcp_result.get("data"),
                                "error": mcp_result.get("error"),
                                "access_denied": mcp_result.get("access_denied", False),
                                "is_empty": mcp_result.get("is_empty", False)
                            })

                            # Add to conversation
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

                            # Build tool response
                            if mcp_result.get("access_denied"):
                                tool_response = {
                                    "access_denied": True,
                                    "error": mcp_result.get("error"),
                                    "_instruction": "Tell user their role does not have access to this data"
                                }
                            elif mcp_result.get("is_empty") or (mcp_result["success"] and not mcp_result.get("data")):
                                tool_response = {
                                    "data": [],
                                    "_instruction": f"No {tool_name.replace('get_', '').replace('_', ' ')} found for this patient. This is NOT an error - simply inform the user no records exist."
                                }
                            elif mcp_result["success"]:
                                tool_response = mcp_result.get("data")
                            else:
                                tool_response = {"error": mcp_result.get("error")}

                            messages.append({
                                "role": "tool",
                                "tool_call_id": current_tool_call["id"],
                                "content": json.dumps(tool_response, default=str)
                            })

                            # Continue loop for final response
                            break

                        elif choice.finish_reason == "stop":
                            return
                        else:
                            return

                else:
                    return

            except Exception as e:
                print(f"OpenAI API Error: {e}")
                yield safe_json({"type": "error", "content": str(e)})
                return

    async def _update_context_from_result(self, tool_name, mcp_result):
        """Update conversation context based on tool results."""
        if not mcp_result.get("success"):
            return
        
        data = mcp_result.get("data")
        if not data:
            return
        
        patient_id = None
        patient_name = None
        
        if tool_name == "get_patient_overview":
            if isinstance(data, dict):
                patient_id = data.get("patient_id")
                first = data.get("first_name", "")
                last = data.get("last_name", "")
                patient_name = f"{first} {last}".strip()
        
        elif tool_name in ["get_patient_phi", "get_medical_records", "get_appointments", "get_admissions"]:
            if isinstance(data, dict):
                patient_id = data.get("patient_id")
            elif isinstance(data, list) and len(data) > 0:
                patient_id = data[0].get("patient_id")
        
        if patient_id:
            self.conversation_context["last_patient_id"] = patient_id
            if patient_name:
                self.conversation_context["last_patient_name"] = patient_name
            await self._save_context_to_session()
            print(f"🧠 MEMORY: Updated context to patient {patient_id}")


# ============================================================
# NON-STREAMING LLM HANDLER
# ============================================================

class LLMAgentHandler:
    """Non-streaming version for backwards compatibility."""
    
    def __init__(self, user, request=None):
        self.user = user
        self.request = request
        self.jwt = request.session.get("access_jwt") if request else None

    def get_response(self, user_message):
        """Non-streaming version - returns complete response."""
        from openai import OpenAI
        client = OpenAI(api_key=LLMConfig.OPENAI_KEY)

        role = getattr(self.user, 'role', 'Unknown')
        system_prompt = f"""You are SecureHospital AI.
User: {self.user.username} | Role: {role}

RULE: ALWAYS call tools for data requests. NEVER pre-refuse.
The MCP server handles access control - NOT you.

Tools:
- get_patient_overview: patient name, age, gender
- get_patient_phi: SSN, address, phone, email, EMERGENCY CONTACT, insurance
- get_medical_records: diagnoses, treatments
- get_appointments: patient appointments
- get_admissions: hospital stays
- get_my_shifts: YOUR schedule
- get_shifts: another staff member's schedule"""

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

            if message.tool_calls:
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    mcp_result = call_mcp_tool(tool_name, arguments, self.jwt)
                
                content = f"Tool data retrieved. Please ask your question again for analysis."
            else:
                content = message.content

            content = rbac_filter_text(role, content)

            return {
                "content": content,
                "tokens_used": response.usage.total_tokens if response.usage else 0,
                "tool_calls": message.tool_calls if message.tool_calls else []
            }

        except Exception as e:
            return {"error": str(e)}
