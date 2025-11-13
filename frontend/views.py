# frontend/views.py
"""
Frontend views for the Secure Hospital system.

Handles:
- Dashboard rendering with CSRF token generation
- Token minting for JWT-based authentication
- MCP proxy endpoint for tool invocation (JWT-based, bypasses CSRF)
- Audit log viewing
- RBAC information display

Architecture:
- Frontend → Django Proxy (/mcp-proxy/) → MCP Server (port 9000)
- All communication uses JWT tokens from secure_hospital_ai/settings.py JWT_SECRET
- MCP server validates JWT and enforces RBAC
- CSRF protection: Disabled for /mcp-proxy/ (API endpoint), enabled for HTML forms
"""

import os, json, requests
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.middleware.csrf import get_token
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status as http_status

from audit.models import AuditLog

# MCP Server endpoint (FastAPI server on port 9000)
MCP_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:9000/mcp/")

@login_required
def dashboard(request):
    # Ensure CSRF cookie for HTMX, and auto-mint token if missing
    get_token(request)
    if "access_jwt" not in request.session:
        token = AccessToken.for_user(request.user)
        request.session["access_jwt"] = str(token)
    # Render dashboard
    return render(request, "dashboard.html")

@login_required
def mint_token(request):
    """
    Mint a new JWT token for the authenticated user.
    
    Returns:
        - token (str): JWT token to use in Authorization header for API calls
        - user_id (str): The authenticated user's ID
        - username (str): The authenticated user's username
        - user_role (str): The user's primary role (from user profile or 'user' default)
    
    Usage:
        Fetch /mint-token/ to get a fresh JWT token
        Use the token in: Authorization: Bearer <token>
    """
    token = AccessToken.for_user(request.user)
    token_str = str(token)
    request.session["access_jwt"] = token_str
    
    # Get user role if available (from user profile or default to 'user')
    user_role = getattr(request.user, 'user_role', 'user')
    if hasattr(request.user, 'profile') and hasattr(request.user.profile, 'role'):
        user_role = request.user.profile.role
    
    return JsonResponse({
        "ok": True,
        "token": token_str,
        "user_id": str(request.user.id),
        "username": request.user.username,
        "user_role": user_role
    })

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mcp_proxy(request):
    """
    JWT-authenticated proxy endpoint for MCP tool calls.
    
    DRF @api_view decorator:
    - Bypasses Django CSRF middleware (API endpoint, not HTML form)
    - Handles OPTIONS preflight for CORS
    - Returns proper HTTP status codes
    
    @authentication_classes([JWTAuthentication]):
    - Validates JWT token from Authorization header
    - Extracts user from token (same JWT_SECRET as MCP server)
    
    @permission_classes([IsAuthenticated]):
    - Ensures user is authenticated before processing
    
    Supports both:
      - application/json body
      - form POST (builds JSON-RPC payload server-side)
    
    Forwards to MCP server with Authorization header containing JWT.
    MCP server (FastAPI on port 9000) validates same JWT and enforces RBAC.
    """
    # Extract JWT token from DRF request.auth (already validated by JWTAuthentication)
    if hasattr(request, 'auth') and request.auth:
        # For SimpleJWT, request.auth is the Token object; str() gives the JWT string
        access_jwt = str(request.auth)
    else:
        # Fallback if token not in Authorization header
        return Response(
            {"error": "No JWT token in Authorization header"},
            status=http_status.HTTP_401_UNAUTHORIZED
        )

    # Read request body
    ctype = request.headers.get("Content-Type", "")
    payload = None

    if "application/json" in ctype:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return Response(
                {"error": "Invalid JSON"},
                status=http_status.HTTP_400_BAD_REQUEST
            )
    else:
        # Form POST (from Quick Tools); build a JSON-RPC payload server-side
        tool = request.POST.get("tool")
        patient_id = request.POST.get("patient_id")
        if not tool:
            return Response(
                {"error": "Missing 'tool'"},
                status=http_status.HTTP_400_BAD_REQUEST
            )
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools.call",
            "params": {"name": tool, "arguments": {}}
        }
        if tool != "get_my_shifts" and patient_id:
            payload["params"]["arguments"]["patient_id"] = patient_id

    # Forward to MCP with Authorization header (same JWT_SECRET)
    try:
        resp = requests.post(
            MCP_URL,
            headers={
                "Authorization": f"Bearer {access_jwt}",
                "Content-Type": "application/json",
                # Helpful provenance for audit logging
                "X-User-Id": str(request.user.pk),
                "X-User-Role": getattr(request.user, "role", ""),
            },
            json=payload,
            timeout=20,
        )
    except requests.RequestException as e:
        return Response(
            {"error": f"MCP unreachable: {e}"},
            status=http_status.HTTP_502_BAD_GATEWAY
        )

    # Relay JSON result from MCP
    try:
        data = resp.json()
    except ValueError:
        return Response(
            {"error": resp.text},
            status=resp.status_code
        )
    return Response(data, status=resp.status_code)

@login_required
def whoami(request):
    user = request.user
    return JsonResponse({
        "username": user.username,
        "role": getattr(user, "role", None),
        "id": str(user.pk),
        "is_authenticated": True,
    })

@login_required
def effective_rbac(request):
    """
    Simple “what can I see” matrix, derived from the role on the Django user.
    Mirrors your MCP RBAC policy so the UI educates the viewer.
    """
    role = getattr(request.user, "role", "")
    # Keep this in sync with MCP’s is_allowed()
    matrix = {
        "Admin":        {"PHI": "view+edit", "Patients": "view+edit", "Records": "view+edit", "Admissions": "view+edit", "Appointments": "view+edit", "Shifts":"view+edit"},
        "Auditor":      {"PHI": "view",      "Patients": "view",      "Records": "view",      "Admissions": "view",      "Appointments": "view",      "Shifts":"view"},
        "Doctor":       {"PHI": "no (via MCP redaction)", "Patients": "view+edit", "Records": "view+edit", "Admissions":"assigned only", "Appointments":"view+edit", "Shifts":"view"},
        "Nurse":        {"PHI": "no (via MCP redaction)", "Patients": "view+edit", "Records":"view", "Admissions":"view", "Appointments":"view+edit", "Shifts":"view"},
        "Billing":      {"PHI": "insurance-only", "Patients":"view", "Records":"no", "Admissions":"view", "Appointments":"view", "Shifts":"no"},
        "Reception":    {"PHI": "no", "Patients":"view+edit (basic)", "Records":"no", "Admissions":"create/view", "Appointments":"create/view", "Shifts":"view"},
    }
    return JsonResponse({"role": role, "effective": matrix.get(role, {})})

@login_required
def audit_latest(request):
    """
    Show latest 25 audit lines filtered to the current user (zero trust UX).
    """
    rows = (AuditLog.objects
            .filter(user=request.user)
            .order_by("-timestamp")[:25]
            .values("timestamp","action","table_name","is_phi_access","ip_address"))
    return JsonResponse({"items": list(rows)})


# ============================================================================
# CHAT API ENDPOINTS
# ============================================================================

@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def chat_session_create(request):
    """
    Create a new chat session for the authenticated user.
    
    Request body:
    {
        "title": "Patient Inquiry - John Doe",
        "context": {"patient_id": "abc123", "department": "Cardiology"}
    }
    
    Response:
    {
        "id": 123,
        "user_id": "...",
        "title": "...",
        "created_at": "2025-11-11T10:00:00Z",
        "context": {}
    }
    """
    from frontend.models import ChatSession
    
    try:
        data = json.loads(request.body.decode('utf-8'))
        title = data.get('title', 'New Chat')
        context = data.get('context', {})
    except json.JSONDecodeError:
        return Response(
            {"error": "Invalid JSON"},
            status=http_status.HTTP_400_BAD_REQUEST
        )
    
    # Create session for authenticated user
    session = ChatSession.objects.create(
        user=request.user,
        title=title,
        context=context
    )
    
    # Log to audit trail
    AuditLog.objects.create(
        user=request.user,
        action="CHAT_SESSION_CREATED",
        table_name="ChatSession",
        record_id=session.id,
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    
    return Response({
        "id": session.id,
        "user_id": str(request.user.pk),
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "context": session.context,
    }, status=http_status.HTTP_201_CREATED)


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def chat_sessions_list(request):
    """
    List all chat sessions for the authenticated user.
    
    Query params:
    - limit: Max results (default 50)
    - offset: Skip first N results (default 0)
    
    Response:
    {
        "total": 5,
        "sessions": [
            {"id": 1, "title": "...", "created_at": "...", "updated_at": "..."},
            ...
        ]
    }
    """
    from frontend.models import ChatSession
    
    limit = int(request.query_params.get('limit', 50))
    offset = int(request.query_params.get('offset', 0))
    
    # Limit to user's own sessions (unless admin)
    query = ChatSession.objects.filter(user=request.user)
    
    total = query.count()
    sessions_list = query[offset:offset+limit].values(
        'id', 'title', 'summary', 'created_at', 'updated_at'
    )
    
    # Convert datetimes to ISO format
    sessions_data = []
    for s in sessions_list:
        s['created_at'] = s['created_at'].isoformat()
        s['updated_at'] = s['updated_at'].isoformat()
        sessions_data.append(s)
    
    return Response({
        "total": total,
        "limit": limit,
        "offset": offset,
        "sessions": sessions_data,
    }, status=http_status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def chat_message_send(request):
    """
    Send a message to the LLM and get a streaming response.
    
    Request body:
    {
        "session_id": 123,
        "message": "What medications is the patient currently on?",
        "stream": true
    }
    
    If stream=true: Returns NDJSON with streaming tokens
    If stream=false: Returns complete response
    
    Response (stream=false):
    {
        "message_id": 456,
        "session_id": 123,
        "role": "assistant",
        "content": "The patient is currently on...",
        "created_at": "2025-11-11T10:05:00Z",
        "tokens_used": 150,
        "cost_cents": 3
    }
    """
    from frontend.models import ChatSession, ChatMessage
    from frontend.llm_handler import LLMAgentHandler, LLMConfig
    
    try:
        data = json.loads(request.body.decode('utf-8'))
        session_id = data.get('session_id')
        message_text = data.get('message')
        stream = data.get('stream', False)
    except json.JSONDecodeError:
        return Response(
            {"error": "Invalid JSON"},
            status=http_status.HTTP_400_BAD_REQUEST
        )
    
    # Validate inputs
    if not session_id or not message_text:
        return Response(
            {"error": "Missing session_id or message"},
            status=http_status.HTTP_400_BAD_REQUEST
        )
    
    # Get session (verify ownership)
    try:
        session = ChatSession.objects.get(id=session_id, user=request.user)
    except ChatSession.DoesNotExist:
        return Response(
            {"error": "Session not found"},
            status=http_status.HTTP_404_NOT_FOUND
        )
    
    # Store user message
    user_message = ChatMessage.objects.create(
        session=session,
        role='user',
        content=message_text,
        user_role_at_time=getattr(request.user, 'role', ''),
    )
    
    # Log user message
    AuditLog.objects.create(
        user=request.user,
        action="CHAT_MESSAGE_SENT",
        table_name="ChatMessage",
        record_id=user_message.id,
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    
    # Get LLM response (with RBAC enforcement)
    try:
        llm_handler = LLMAgentHandler(request.user, request=request)
        
        if stream:
            # Return streaming response
            from django.http import StreamingHttpResponse
            
            def generate():
                """Stream response tokens as NDJSON"""
                full_response = ""
                tool_calls = []
                tool_results = []
                tokens_used = 0
                cost_cents = 0
                
                # Stream from LLM
                for chunk_json in llm_handler.stream_response(user_message=message_text):
                    try:
                        chunk = json.loads(chunk_json)
                        
                        if chunk.get("type") == "message":
                            content = chunk.get("content", "")
                            full_response += content
                            yield json.dumps({
                                "event": "token",
                                "delta": content
                            }) + "\n"
                        
                        elif chunk.get("type") == "tool_call":
                            tool_calls.append(chunk.get("content", {}))
                            yield json.dumps({
                                "event": "tool_call",
                                "tool": chunk.get("content", {})
                            }) + "\n"
                        
                        elif chunk.get("type") == "tool_result":
                            # NEW: Handle tool execution results
                            tool_result_event = {
                                "event": "tool_result",
                                "tool_name": chunk.get("tool_name"),
                                "success": chunk.get("success"),
                                "data": chunk.get("data"),
                                "error": chunk.get("error")
                            }
                            tool_results.append(tool_result_event)
                            yield json.dumps(tool_result_event) + "\n"
                        
                        elif chunk.get("type") == "error":
                            yield json.dumps({"error": chunk.get("content", "Unknown error")}) + "\n"
                    except json.JSONDecodeError:
                        continue
                
                # Store assistant response
                assistant_message = ChatMessage.objects.create(
                    session=session,
                    role='assistant',
                    content=full_response,
                    is_streamed=True,
                    model_used=LLMConfig.MODEL if hasattr(LLMConfig, 'MODEL') else 'gpt-4-turbo',
                    tokens_used=tokens_used,
                    cost_cents=cost_cents,
                    tool_calls=tool_calls,
                    user_role_at_time=getattr(request.user, 'role', ''),
                )
                
                # Final done message
                yield json.dumps({
                    "event": "done",
                    "message_id": assistant_message.id,
                    "tokens_used": tokens_used,
                    "cost_cents": cost_cents
                }) + "\n"
                
                # Log to audit
                AuditLog.objects.create(
                    user=request.user,
                    action="CHAT_RESPONSE_RECEIVED",
                    table_name="ChatMessage",
                    record_id=assistant_message.id,
                    ip_address=request.META.get('REMOTE_ADDR'),
                )
            
            return StreamingHttpResponse(
                generate(),
                content_type='application/x-ndjson',
                status=200
            )
        
        else:
            # Non-streaming: get complete response
            response_data = llm_handler.get_response(
                user_message=message_text
            )
            
            if response_data.get('error'):
                return Response(
                    {"error": response_data['error']},
                    status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Store assistant message
            assistant_message = ChatMessage.objects.create(
                session=session,
                role='assistant',
                content=response_data.get('content', ''),
                is_streamed=False,
                model_used=LLMConfig.MODEL if hasattr(LLMConfig, 'MODEL') else 'gpt-4-turbo',
                tokens_used=response_data.get('tokens_used', 0),
                cost_cents=response_data.get('cost_cents', 0),
                tool_calls=response_data.get('tool_calls', []),
                user_role_at_time=getattr(request.user, 'role', ''),
            )
            
            # Log to audit
            AuditLog.objects.create(
                user=request.user,
                action="CHAT_RESPONSE_RECEIVED",
                table_name="ChatMessage",
                record_id=assistant_message.id,
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            
            return Response({
                "message_id": assistant_message.id,
                "session_id": session.id,
                "role": "assistant",
                "content": assistant_message.content,
                "created_at": assistant_message.created_at.isoformat(),
                "tokens_used": assistant_message.tokens_used,
                "cost_cents": assistant_message.cost_cents,
                "tool_calls": assistant_message.tool_calls,
            }, status=http_status.HTTP_200_OK)
    
    except Exception as e:
        return Response(
            {"error": f"LLM error: {str(e)}"},
            status=http_status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def chat_history(request):
    """
    Get conversation history for a session.
    
    Query params:
    - session_id: Session to retrieve messages from
    - limit: Max results (default 100)
    
    Response:
    {
        "session_id": 123,
        "messages": [
            {
                "id": 456,
                "role": "user",
                "content": "...",
                "created_at": "...",
                "tokens_used": null
            },
            {
                "id": 457,
                "role": "assistant",
                "content": "...",
                "created_at": "...",
                "tokens_used": 150
            }
        ]
    }
    """
    from frontend.models import ChatSession, ChatMessage
    
    session_id = request.query_params.get('session_id')
    limit = int(request.query_params.get('limit', 100))
    
    if not session_id:
        return Response(
            {"error": "Missing session_id"},
            status=http_status.HTTP_400_BAD_REQUEST
        )
    
    # Get session (verify ownership)
    try:
        session = ChatSession.objects.get(id=session_id, user=request.user)
    except ChatSession.DoesNotExist:
        return Response(
            {"error": "Session not found"},
            status=http_status.HTTP_404_NOT_FOUND
        )
    
    # Get messages (newest first)
    messages = ChatMessage.objects.filter(session=session).order_by('-created_at')[:limit]
    
    messages_data = []
    for msg in reversed(messages):  # Reverse to get chronological order
        messages_data.append({
            "id": msg.id,
            "role": msg.role,
            "content": msg.content,
            "created_at": msg.created_at.isoformat(),
            "tokens_used": msg.tokens_used,
            "cost_cents": msg.cost_cents,
            "tool_calls": msg.tool_calls,
        })
    
    return Response({
        "session_id": session.id,
        "total": session.messages.count(),
        "messages": messages_data,
    }, status=http_status.HTTP_200_OK)
