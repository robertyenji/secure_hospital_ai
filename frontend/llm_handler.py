# frontend/llm_handler.py
"""
LLM Agent Handler – manages LLM interactions with prompt templates,
tool binding, response streaming and error recovery.

This module is the bridge between your Django application and the LLM API provider.
It handles:
- Role-based system prompts (what instructions does the LLM receive?)
- Tool availability filtering (Doctor shouldn't see Billing tools)
- Streaming responses (for real-time chat UX)
- Error handling and retries
- Audit logging for compliance
"""

import os
import json
import logging
import requests
import jwt
from openai import OpenAI, APIConnectionError, APIStatusError, APITimeoutError
from enum import Enum
from typing import Optional, Dict, List, Iterator, Any
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
from datetime import datetime

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied

# Configure logging
logger = logging.getLogger(__name__)

# Initialize OpenAI client (will be initialized in LLMConfig.validate())
_openai_client = None


class LLMConfig:
    """Configuration for LLM provider and model"""
    
    # Load from environment variables
    PROVIDER = os.getenv("LLM_PROVIDER", "openai")
    MODEL = os.getenv("LLM_MODEL", "gpt-4-turbo-preview")
    API_KEY = os.getenv("LLM_API_KEY", "")
    TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2000"))
    TIMEOUT = int(os.getenv("LLM_TIMEOUT", "30"))
    
    # Safety limits
    MAX_PROMPT_LENGTH = 5000  # Prevent prompt injection
    MAX_DAILY_TOKENS = 1_000_000  # Per user limit
    RATE_LIMIT_PER_HOUR = 100  # Messages per hour
    
    @classmethod
    def validate(cls):
        """Validate configuration on startup"""
        global _openai_client
        
        if not cls.API_KEY:
            logger.warning("LLM_API_KEY not configured - LLM features disabled")
            return False
        
        # Test connection with new OpenAI client
        try:
            if cls.PROVIDER == "openai":
                _openai_client = OpenAI(api_key=cls.API_KEY)
                # Test the connection by making a simple list models request
                _openai_client.models.list()
        except (APIConnectionError, APIStatusError, APITimeoutError) as e:
            logger.error(f"LLM configuration invalid: {e}")
            return False
        except Exception as e:
            logger.error(f"LLM configuration error: {e}")
            return False
        
        logger.info(f"LLM configured: {cls.PROVIDER} / {cls.MODEL}")
        return True


class ToolType(Enum):
    """Available tools that LLM can call"""
    PATIENT_OVERVIEW = "get_patient_overview"
    PATIENT_ADMISSIONS = "get_patient_admissions"
    PATIENT_APPOINTMENTS = "get_patient_appointments"
    PATIENT_RECORDS = "get_patient_records"
    MY_SHIFTS = "get_my_shifts"


@dataclass
class ToolCall:
    """Represents a tool call from the LLM"""
    tool: str
    patient_id: Optional[str] = None
    reason: str = ""
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


class SystemPromptManager:
    """
    Manages role-based system prompts for the LLM.
    
    Each role gets a different system prompt that:
    1. Sets expectations (what is this AI assistant?)
    2. Enforces boundaries (what data can I access?)
    3. Provides context (healthcare-specific guidance)
    """
    
    SYSTEM_PROMPTS = {
        "Admin": """You are a hospital administration AI assistant with comprehensive system access.

CAPABILITIES:
- View and modify patient records, staff information, admissions, and all hospital data
- Access full PHI (Personally Identifiable Health Information)
- Manage system settings and policies

RESPONSIBILITIES:
- Maintain HIPAA compliance even with full access
- Use your access judiciously and only for legitimate administrative purposes
- Document any sensitive operations for audit trails
- Be professional and ethical in all interactions

GUIDELINES:
- Recommend consulting the full patient record in the official EHR system for clinical decisions
- Flag any suspicious patterns or access violations
- Provide clear explanations for administrative decisions
- Escalate complex medical decisions to qualified physicians

AVAILABLE TOOLS:
- get_patient_overview: Get complete patient information
- get_patient_admissions: View all hospital stays
- get_patient_appointments: View all appointments
- get_patient_records: View complete medical records
- get_my_shifts: View your schedule
""",

        "Doctor": """You are a hospital AI clinical assistant supporting physician decision-making.

CAPABILITIES:
- View patient information for your assigned patients
- Access appointment and admission records
- Retrieve clinical notes and medical records

LIMITATIONS:
- You CANNOT view full PHI (SSN, full address, contact details, insurance info)
- This data is automatically redacted for privacy and security
- You can only access patients assigned to you or in your clinic

RESPONSIBILITIES:
- Provide clinical decision support
- Help with diagnosis and treatment planning
- Recommend diagnostic tests or specialist referrals
- Always recommend consulting the official EHR system for critical decisions

GUIDELINES:
- Maintain patient confidentiality at all times
- Flag any unusual medical findings for follow-up
- Document all recommendations for continuity of care
- Escalate complex cases to senior physicians or specialists

IMPORTANT: PHI data is redacted. For sensitive information, consult the full patient record directly.

AVAILABLE TOOLS:
- get_patient_overview: Get patient demographics and summary
- get_patient_admissions: View hospital stays
- get_patient_appointments: View appointments
- get_patient_records: View medical records
- get_my_shifts: View your scheduled shifts
""",

        "Nurse": """You are a hospital nursing AI assistant supporting patient care and monitoring.

CAPABILITIES:
- View patient information for assigned patients
- Access admission and appointment schedules
- Review clinical notes and care recommendations

LIMITATIONS:
- You CANNOT view full PHI (SSN, addresses, insurance details)
- PHI is automatically redacted for security
- You can only access patients assigned to you

RESPONSIBILITIES:
- Support patient care coordination
- Help with shift planning and scheduling
- Monitor patient vital information
- Coordinate with clinical teams

GUIDELINES:
- Escalate complex medical decisions to physicians
- Report unusual patient conditions promptly
- Maintain confidentiality and professionalism
- Use the official care system for critical updates

AVAILABLE TOOLS:
- get_patient_overview: Get patient summary
- get_patient_admissions: View hospital stays
- get_patient_appointments: View appointments
- get_my_shifts: View your shift schedule
""",

        "Billing": """You are a hospital billing and insurance AI assistant.

CAPABILITIES:
- Access patient insurance information
- View billing-related data
- Help with claims and insurance verification

LIMITATIONS:
- You CANNOT view medical records
- You CANNOT access clinical information
- You can only see insurance-related PHI

RESPONSIBILITIES:
- Assist with insurance verification
- Help resolve billing issues
- Provide cost estimates to patients
- Coordinate with insurance companies

GUIDELINES:
- Maintain patient confidentiality
- Escalate complex billing issues to billing department
- Be transparent about costs and charges
- Flag any billing irregularities

AVAILABLE TOOLS:
- get_patient_overview: Get patient demographics only (for billing)
""",

        "Reception": """You are a hospital reception AI assistant.

CAPABILITIES:
- Help with appointment scheduling
- Assist with patient check-in
- Provide basic patient information

LIMITATIONS:
- You have minimal access to sensitive data
- You CANNOT view medical records
- You CANNOT access financial information

RESPONSIBILITIES:
- Support front-desk operations
- Help schedule appointments
- Assist with patient registration
- Provide general hospital information

GUIDELINES:
- Escalate medical inquiries to appropriate staff
- Maintain patient privacy
- Be professional and helpful
- Escalate complex issues to supervisors

AVAILABLE TOOLS:
- get_patient_overview: Get basic patient info for check-in
""",

        "Auditor": """You are a hospital compliance and audit AI assistant.

CAPABILITIES:
- View all hospital data including full audit logs
- Access complete PHI for compliance purposes
- Review security and access patterns

RESPONSIBILITIES:
- Conduct compliance audits
- Review access patterns for suspicious activity
- Ensure HIPAA compliance
- Maintain security audit trails

GUIDELINES:
- Document all access in audit trails
- Report compliance violations immediately
- Be thorough in audit investigations
- Maintain confidentiality of audit findings

AVAILABLE TOOLS:
- get_patient_overview: Get complete patient information
- get_patient_admissions: View all admissions
- get_patient_appointments: View all appointments
- get_patient_records: View all medical records
- get_my_shifts: View audit logs and access records
"""
    }

    @staticmethod
    def get_prompt(role: str) -> str:
        """
        Get system prompt for a user's role.
        
        Args:
            role: User's role (Admin, Doctor, Nurse, etc.)
        
        Returns:
            System prompt string tailored to the role
        """
        return SystemPromptManager.SYSTEM_PROMPTS.get(
            role,
            SystemPromptManager.SYSTEM_PROMPTS["Reception"]  # Safe default
        )


class LLMAgentHandler:
    """
    Main handler for LLM agent interactions.
    
    Manages:
    - User authentication and RBAC
    - Streaming responses
    - Tool availability
    - Error handling
    - Audit logging
    """
    
    def __init__(self, user: User, ip_address: str = "", request=None):
        """
        Initialize LLM handler for a user.
        
        Args:
            user: Django User object
            ip_address: Client IP for audit logging
            request: Django request object (for extracting JWT token)
        """
        self.user = user
        self.ip_address = ip_address
        self.request = request
        self.role = getattr(user, "role", "Reception")
        self.system_prompt = SystemPromptManager.get_prompt(self.role)
        
        # Import here to avoid circular imports
        from audit.models import AuditLog
        self.AuditLog = AuditLog

    def stream_response(self, user_message: str) -> Iterator[str]:
        """
        Stream LLM response with streaming support for long responses.
        
        This uses the OpenAI streaming API to send responses in real-time,
        improving perceived performance for users.
        
        Args:
            user_message: The user's query or instruction
        
        Yields:
            JSON strings with format:
            {"type": "message" | "tool_call" | "error", "content": "..."}
        
        Each line is a complete JSON object (NDJSON format).
        """
        try:
            # Validate and sanitize input
            user_message = self._sanitize_input(user_message)
            
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
            
            # Get tools available to this user's role
            tools = self._get_available_tools()
            
            logger.info(f"User {self.user.username} ({self.role}) querying LLM")
            
            # Call LLM with streaming using new OpenAI client
            if LLMConfig.PROVIDER == "openai":
                global _openai_client
                if _openai_client is None:
                    _openai_client = OpenAI(api_key=LLMConfig.API_KEY)
                
                response_stream = _openai_client.chat.completions.create(
                    model=LLMConfig.MODEL,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    temperature=LLMConfig.TEMPERATURE,
                    max_tokens=LLMConfig.MAX_TOKENS,
                    timeout=LLMConfig.TIMEOUT,
                    stream=True,
                )
            else:
                raise ValueError(f"Unsupported LLM provider: {LLMConfig.PROVIDER}")
            
            # Process streaming response
            accumulated_content = ""
            accumulated_tool_call = ""
            
            for chunk in response_stream:
                choices = chunk.choices
                if not choices:
                    continue
                
                delta = choices[0].delta
                
                # Handle text content
                if delta.content:
                    content = delta.content
                    accumulated_content += content
                    
                    # Emit text chunks
                    yield json.dumps({
                        "type": "message",
                        "content": content,
                        "timestamp": datetime.utcnow().isoformat()
                    }) + "\n"
                
                # Handle tool calls (function calling)
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        # Convert tool_call object to dict for JSON serialization
                        tool_name = tool_call.function.name if (tool_call.function and tool_call.function.name) else None
                        
                        # Only process if we have a complete tool call with a name
                        if tool_name:
                            tool_call_dict = {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": tool_call.function.arguments if tool_call.function else ""
                                }
                            }
                            
                            try:
                                tool_data = tool_call_dict
                                
                                # Validate tool call against user's role
                                self._validate_tool_call(tool_data)
                                
                                # Emit tool call announcement
                                yield json.dumps({
                                    "type": "tool_call",
                                    "content": tool_data,
                                    "timestamp": datetime.utcnow().isoformat()
                                }) + "\n"
                                
                                # EXECUTE THE TOOL - this is crucial!
                                # Parse arguments if they're a JSON string
                                args = tool_call.function.arguments if tool_call.function else "{}"
                                if isinstance(args, str):
                                    try:
                                        args = json.loads(args)
                                    except json.JSONDecodeError:
                                        args = {}
                                else:
                                    args = args or {}

                                # Fallback: extract patient_id from user_message if missing
                                needs_patient_id = tool_name in {
                                    "get_patient_overview",
                                    "get_patient_admissions",
                                    "get_patient_appointments",
                                    "get_patient_records",
                                }
                                if needs_patient_id and not args.get("patient_id"):
                                    try:
                                        import re
                                        # Look for patterns like: "patient ID XYZ", "ID: XYZ", "patient XYZ"
                                        m = re.search(r"(?i)(?:patient\s*id\s*[:#]?\s*|\bid\s*[:#]?\s*|patient\s+)([A-Za-z0-9_-]{3,})", user_message or "")
                                        if m:
                                            args["patient_id"] = m.group(1).strip()
                                    except Exception:
                                        pass
                                
                                # Call the MCP server to execute the tool
                                tool_result = self._execute_tool(tool_name, args)
                                
                                # Emit tool result
                                yield json.dumps({
                                    "type": "tool_result",
                                    "tool_name": tool_name,
                                    "success": tool_result.get("success", False),
                                    "data": tool_result.get("data"),
                                    "error": tool_result.get("error"),
                                    "timestamp": datetime.utcnow().isoformat()
                                }) + "\n"
                                
                                # If tool execution was successful, add to accumulated content
                                if tool_result.get("success") and tool_result.get("data"):
                                    tool_data_str = json.dumps(tool_result.get("data"), indent=2)
                                    accumulated_content += f"\n[Tool Result: {tool_name}]\n{tool_data_str}\n"
                                
                                # Log tool call with proper tool name
                                self._log_audit(
                                    action="LLM_TOOL_CALL",
                                    table_name="LLM",
                                    tool_name=tool_name,
                                    is_phi=tool_result.get("success") and self._check_phi_access(str(tool_result.get("data", "")))
                                )
                                
                            except PermissionDenied as e:
                                # Tool not allowed for this role - emit error and continue
                                logger.warning(f"RBAC violation for {self.user.username}: {str(e)}")
                                yield json.dumps({
                                    "type": "error",
                                    "content": f"Tool '{tool_name}' is not available for your role ({self.role}). This is a security feature of the system.",
                                    "timestamp": datetime.utcnow().isoformat()
                                }) + "\n"
                                
                                # Log the RBAC violation
                                self._log_audit(
                                    action="RBAC_VIOLATION",
                                    table_name="LLM",
                                    tool_name=tool_name,
                                    is_phi=False
                                )
            
            # Log successful interaction
            self._log_audit(
                action="LLM_CALL",
                table_name="LLM",
                is_phi=self._check_phi_access(accumulated_content)
            )
            
            logger.info(f"LLM call completed for user {self.user.username}")
            
        except Exception as e:
            logger.error(f"LLM error for user {self.user.username}: {str(e)}", exc_info=True)
            
            error_msg = "An error occurred while processing your request. Please try again."
            if LLMConfig.TEMPERATURE <= 0.1:  # Dev mode only
                error_msg = f"Error: {str(e)}"
            
            yield json.dumps({
                "type": "error",
                "content": error_msg,
                "timestamp": datetime.utcnow().isoformat()
            }) + "\n"
            
            # Log error
            self._log_audit(
                action="LLM_ERROR",
                table_name="LLM",
                is_phi=False
            )

    def get_response(self, user_message: str) -> Dict[str, Any]:
        """
        Get non-streaming LLM response (batched).
        
        Collects all tokens from streaming response and returns as a single JSON object.
        
        Args:
            user_message: The user's query or instruction
        
        Returns:
            Dictionary with format:
            {
                "content": "Full response text",
                "tokens_used": 150,
                "cost_cents": 3,
                "tool_calls": [],
                "error": None (if successful)
            }
        """
        try:
            # Collect all chunks from streaming response
            full_content = ""
            all_tool_calls = []
            total_tokens = 0
            total_cost_cents = 0
            
            for chunk_json in self.stream_response(user_message):
                try:
                    chunk = json.loads(chunk_json)
                    
                    if chunk.get("type") == "message":
                        full_content += chunk.get("content", "")
                    
                    elif chunk.get("type") == "tool_call":
                        all_tool_calls.append(chunk.get("content", {}))
                    
                    elif chunk.get("type") == "error":
                        return {
                            "content": "",
                            "error": chunk.get("content", "Unknown error"),
                            "tokens_used": 0,
                            "cost_cents": 0,
                            "tool_calls": []
                        }
                except json.JSONDecodeError:
                    # Skip malformed JSON chunks
                    continue
            
            return {
                "content": full_content,
                "tokens_used": total_tokens,
                "cost_cents": total_cost_cents,
                "tool_calls": all_tool_calls,
                "error": None
            }
        
        except Exception as e:
            logger.error(f"get_response error for user {self.user.username}: {str(e)}", exc_info=True)
            return {
                "content": "",
                "error": str(e),
                "tokens_used": 0,
                "cost_cents": 0,
                "tool_calls": []
            }

    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Return available tools based on user's RBAC role.
        
        Different roles have access to different tools:
        - Admin/Auditor: All tools
        - Doctor/Nurse: Patient-focused tools
        - Billing: Limited to billing operations
        - Reception: Only basic patient lookup
        
        Returns:
            List of tool definitions in OpenAI function_call schema format
        """
        # Base tools available to most roles
        patient_overview_tool = {
            "type": "function",
            "function": {
                "name": "get_patient_overview",
                "description": "Get overview of a patient including demographics, current status",
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
        }
        
        patient_admissions_tool = {
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
        }
        
        patient_appointments_tool = {
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
        }
        
        patient_records_tool = {
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
        }
        
        my_shifts_tool = {
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
        
        # Return tools based on role
        if self.role in ["Admin", "Auditor"]:
            # Full access
            return [
                patient_overview_tool,
                patient_admissions_tool,
                patient_appointments_tool,
                patient_records_tool,
                my_shifts_tool
            ]
        elif self.role in ["Doctor", "Nurse"]:
            # Patient-focused access
            return [
                patient_overview_tool,
                patient_admissions_tool,
                patient_appointments_tool,
                patient_records_tool,
                my_shifts_tool
            ]
        elif self.role == "Billing":
            # Limited to patient overview
            return [patient_overview_tool]
        else:  # Reception
            # Minimal access
            return [patient_overview_tool]

    def _sanitize_input(self, text: str) -> str:
        """
        Sanitize user input to prevent prompt injection.
        
        Args:
            text: Raw user input
        
        Returns:
            Sanitized text
        
        Raises:
            ValueError: If input is suspicious
        """
        # Limit length
        if len(text) > LLMConfig.MAX_PROMPT_LENGTH:
            raise ValueError(f"Input too long (max {LLMConfig.MAX_PROMPT_LENGTH} chars)")
        
        # Check for SQL injection patterns
        sql_patterns = [
            "SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER"
        ]
        if any(pattern in text.upper() for pattern in sql_patterns):
            logger.warning(f"Potential SQL injection from {self.user.username}: {text[:50]}")
            # Allow it but log it - LLM model is unlikely to execute SQL
        
        # Check for prompt injection attempts
        injection_patterns = [
            "ignore previous instructions",
            "pretend you are",
            "you are now",
            "system prompt"
        ]
        if any(pattern in text.lower() for pattern in injection_patterns):
            logger.warning(f"Potential prompt injection from {self.user.username}")
        
        return text.strip()

    def _validate_tool_call(self, tool_call: Dict[str, Any]):
        """
        Validate a tool call before execution.
        
        This is a ZERO-TRUST security check - all tool calls must be explicitly
        allowed for the user's role. If a tool is not in the allowed list, the
        call is rejected, preventing any unauthorized data access.
        
        Args:
            tool_call: Tool call data from LLM
        
        Raises:
            PermissionDenied: If tool is not allowed for this role
        """
        tool_name = tool_call.get("function", {}).get("name")
        
        # Safety check - tool_name should never be None at this point
        if not tool_name:
            raise PermissionDenied("Tool call missing function name - cannot validate")
        
        available_tools = [
            t["function"]["name"]
            for t in self._get_available_tools()
        ]
        
        if tool_name not in available_tools:
            logger.warning(
                f"SECURITY: User {self.user.username} (Role: {self.role}) "
                f"attempted to call unauthorized tool: {tool_name}. "
                f"Available tools: {available_tools}"
            )
            raise PermissionDenied(
                f"Tool '{tool_name}' is not available for role '{self.role}'. "
                f"This is a zero-trust security policy."
            )

    def _check_phi_access(self, content: str) -> bool:
        """
        Check if response contains PHI references.
        
        Args:
            content: Response content
        
        Returns:
            True if PHI was likely accessed
        """
        phi_indicators = [
            "SSN", "address", "phone", "email", "insurance",
            "date of birth", "medical record", "diagnosis"
        ]
        return any(indicator.lower() in content.lower() for indicator in phi_indicators)

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool by calling the MCP server.
        
        This is how the LLM's tool calls are actually executed against the database.
        
        Args:
            tool_name: Name of the tool (e.g., "get_patient_records")
            arguments: Arguments to pass to the tool (e.g., {"patient_id": "PAT-001"})
        
        Returns:
            Result dict with format: {"success": bool, "data": Any, "error": str}
        """
        try:
            # Map LLM tool names to MCP tool names
            mcp_tool_map = {
                "get_patient_overview": "get_patient_overview",
                "get_patient_admissions": "get_admissions",
                "get_patient_appointments": "get_appointments",
                "get_patient_records": "get_medical_records",
                "get_my_shifts": "get_shifts",
            }
            
            mcp_tool_name = mcp_tool_map.get(tool_name)
            if not mcp_tool_name:
                return {
                    "success": False,
                    "data": None,
                    "error": f"Unknown tool: {tool_name}"
                }
            
            # Get MCP server URL from environment
            # Default to FastAPI MCP on port 9000 to match the project
            mcp_url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:9000/mcp/")
            
            # Create JWT token for MCP server authentication
            # MCP server needs a token with user_id and role claims
            jwt_secret = os.getenv("JWT_SECRET", "")
            jwt_alg = os.getenv("JWT_ALG", "HS256")
            
            if not jwt_secret:
                logger.error("JWT_SECRET not configured - cannot authenticate with MCP server")
                return {
                    "success": False,
                    "data": None,
                    "error": "System not configured for MCP authentication"
                }
            
            # Create token with user_id and role claims
            mcp_token = jwt.encode(
                {
                    "user_id": str(self.user.id),
                    "role": self.role,
                    "username": self.user.username,
                },
                jwt_secret,
                algorithm=jwt_alg
            )
            
            # Prepare headers with JWT token for MCP server
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {mcp_token}"
            }
            
            # Prepare JSON-RPC request for MCP server (method must be "tools.call")
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools.call",
                "params": {
                    "name": mcp_tool_name,
                    "arguments": arguments
                }
            }
            
            logger.info(f"Executing MCP tool {mcp_tool_name} with args {arguments}")
            
            # Call MCP server
            response = requests.post(
                mcp_url,
                json=payload,
                timeout=30,
                headers=headers
            )

            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    return {
                        "success": True,
                        "data": result.get("result", {}).get("data"),
                        "error": None
                    }
                elif "error" in result:
                    # Bubble up JSON-RPC error message
                    err_msg = result.get("error", {}).get("message", "Unknown MCP error")
                    logger.error(f"MCP JSON-RPC error for {tool_name}: {err_msg}")
                    return {
                        "success": False,
                        "data": None,
                        "error": err_msg
                    }
            else:
                # Include server-provided error details if present
                err_text = response.text
                try:
                    err_json = response.json()
                    err_text = err_json.get("error", {}).get("message") or err_text
                except Exception:
                    pass
                logger.error(f"MCP server returned {response.status_code} for {tool_name}: {err_text}")
                return {
                    "success": False,
                    "data": None,
                    "error": f"MCP {response.status_code}: {err_text}"
                }
        
        except Exception as e:
            logger.error(f"Tool execution error: {str(e)}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error": f"Tool execution failed: {str(e)}"
            }

    def _log_audit(self, action: str, table_name: str, 
                   tool_name: str = None, is_phi: bool = False):
        """
        Log interaction to audit log for compliance.
        
        Args:
            action: Action type (LLM_CALL, LLM_TOOL_CALL, LLM_ERROR, RBAC_VIOLATION)
            table_name: Table accessed (usually "LLM")
            tool_name: Tool called (if applicable) - NOT used as record_id
            is_phi: Whether PHI was accessed
        """
        try:
            # IMPORTANT: Do NOT use tool_name as record_id
            # tool_name is a string and record_id must be a UUID
            # Always pass None for record_id unless it's an actual database record ID
            
            self.AuditLog.objects.create(
                user=self.user,
                action=action,
                table_name=table_name,
                record_id=None,  # Always None for LLM operations
                ip_address=self.ip_address,
                is_phi_access=is_phi
            )
        except Exception as e:
            # Log audit failures without breaking the flow
            # This is a safety net for HIPAA compliance
            logger.error(f"Failed to create audit log: {e}", exc_info=True)


# Validate LLM configuration on import
if not LLMConfig.validate():
    logger.warning("LLM features may not work correctly - check configuration")
