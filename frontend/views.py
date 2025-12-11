# frontend/views.py
"""
SecureHospital AI - Frontend Views with Three-Layer RBAC
========================================================
- Layer 1: Django/Frontend pre-flight RBAC check
- Supports SSE streaming chat with MCP tool integration
- Complete audit logging
- Documentation, sample data, demo accounts APIs

FIXED:
- Logout redirect
- RBAC pre-check before LLM
- Audit log details
"""

import os
import json
import requests
import re
from django.shortcuts import render, redirect
from django.http import JsonResponse, StreamingHttpResponse, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout as auth_logout, get_user_model
from django.contrib import messages
from django.middleware.csrf import get_token
from django.conf import settings
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework import status as http_status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import AccessToken

from audit.models import AuditLog
from frontend.models import ChatSession, ChatMessage
from frontend.llm_handler import LLMAgentHandler, StreamingLLMAgent, LLMConfig
from django.views.decorators.csrf import csrf_exempt
from openai import OpenAI

# Import RBAC configuration (Layer 1)
try:
    from frontend.rbac import (
        ROLES, TOOL_PERMISSIONS, PHI_ACCESS_LEVELS,
        can_access_tool, get_phi_access_level, get_rbac_matrix_for_display,
        get_rbac_prompt_for_role, check_tool_access
    )
except ImportError:
    # Fallback if rbac.py not yet created
    ROLES = ["Admin", "Doctor", "Nurse", "Auditor", "Reception", "Billing"]
    TOOL_PERMISSIONS = {}
    def can_access_tool(role, tool): return True
    def get_rbac_matrix_for_display(): return {}

User = get_user_model()

# MCP server endpoint
MCP_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:9000/mcp/")


# ======================================================
# HELPERS
# ======================================================

def get_client_ip(request):
    """Extract client IP from request headers."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def sse(event, data):
    """Formats SSE event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ======================================================
# MAIN PAGES
# ======================================================

def landing_page(request):
    """Homepage with project overview"""
    if request.user.is_authenticated:
        return redirect('frontend:dashboard')
    return render(request, 'landing.html')


def login_view(request):
    """Login page with demo account support."""
    if request.user.is_authenticated:
        return redirect('frontend:dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {username}!')
            return redirect('frontend:dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'login.html')


# ======================================================
# LEGAL PAGES
# ======================================================

def privacy_policy(request):
    """Privacy Policy page."""
    return render(request, 'privacy_policy.html')


def terms_of_service(request):
    """Terms of Service page."""
    return render(request, 'terms_of_service.html')


def disclaimer(request):
    """Disclaimer page."""
    return render(request, 'disclaimer.html')


# ======================================================
# DOCUMENTATION PAGES
# ======================================================

def documentation(request):
    """Main documentation page with setup instructions."""
    return render(request, 'documentation.html')


def api_reference(request):
    """API reference page."""
    return render(request, 'api_reference.html')


# ======================================================
# LOGOUT (FIXED)
# ======================================================

@login_required
def logout_view(request):
    """
    Logout user and redirect to landing page.
    Creates audit log entry for the logout.
    """
    user = request.user
    ip = get_client_ip(request)
    
    # Log the logout
    try:
        AuditLog.objects.create(
            user=user,
            action="LOGOUT",
            table_name="auth",
            timestamp=timezone.now(),
            ip_address=ip,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
        )
    except Exception as e:
        print(f"Audit log error: {e}")
    
    # Perform logout
    auth_logout(request)
    
    # Redirect to landing page
    return redirect('frontend:landing')


# ======================================================
# RBAC API ENDPOINTS
# ======================================================

@api_view(["GET"])
@permission_classes([AllowAny])
def rbac_matrix(request):
    """
    Get RBAC matrix for display on landing page.
    Public endpoint - no authentication required.
    """
    try:
        matrix_data = get_rbac_matrix_for_display()
        return Response(matrix_data)
    except Exception as e:
        # Fallback static matrix if rbac.py fails
        return Response({
            "roles": [
                {"id": "Admin", "description": "Full system access"},
                {"id": "Doctor", "description": "Full clinical access"},
                {"id": "Nurse", "description": "Clinical care, redacted PHI"},
                {"id": "Auditor", "description": "Read-only compliance"},
                {"id": "Reception", "description": "Front desk, appointments"},
                {"id": "Billing", "description": "Insurance info only"},
            ],
            "matrix": [
                {
                    "tool": {"id": "get_patient_overview", "name": "Patient Overview"},
                    "permissions": {
                        "Admin": "✅", "Doctor": "✅", "Nurse": "✅",
                        "Auditor": "✅", "Reception": "✅", "Billing": "✅"
                    }
                },
                {
                    "tool": {"id": "get_medical_records", "name": "Medical Records"},
                    "permissions": {
                        "Admin": "✅", "Doctor": "✅", "Nurse": "✅",
                        "Auditor": "✅", "Reception": "❌", "Billing": "❌"
                    }
                },
                {
                    "tool": {"id": "get_patient_phi", "name": "PHI Access"},
                    "permissions": {
                        "Admin": "✅ Full", "Doctor": "✅ Full", "Nurse": "⚠️ Redacted",
                        "Auditor": "✅ Full", "Reception": "❌", "Billing": "💳 Insurance"
                    }
                },
                {
                    "tool": {"id": "get_appointments", "name": "Appointments"},
                    "permissions": {
                        "Admin": "✅", "Doctor": "✅", "Nurse": "✅",
                        "Auditor": "✅", "Reception": "✅", "Billing": "❌"
                    }
                },
                {
                    "tool": {"id": "get_admissions", "name": "Admissions"},
                    "permissions": {
                        "Admin": "✅", "Doctor": "✅", "Nurse": "✅",
                        "Auditor": "✅", "Reception": "❌", "Billing": "❌"
                    }
                },
            ]
        })


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def my_permissions(request):
    """
    Get current user's RBAC permissions.
    Requires authentication.
    """
    user = request.user
    role = getattr(user, 'role', None)
    
    if not role:
        return Response({"error": "No role assigned"}, status=400)
    
    try:
        from frontend.rbac import get_allowed_tools, get_denied_tools, get_phi_access_level
        
        allowed = get_allowed_tools(role)
        denied = get_denied_tools(role)
        phi_level = get_phi_access_level(role)
        
        return Response({
            "username": user.username,
            "role": role,
            "allowed_tools": allowed,
            "denied_tools": denied,
            "phi_access_level": phi_level.value if hasattr(phi_level, 'value') else str(phi_level),
        })
    except ImportError:
        return Response({
            "username": user.username,
            "role": role,
            "message": "RBAC module not fully configured"
        })


# ======================================================
# TOKEN CREATION
# ======================================================

def create_token_with_role(user):
    """Create JWT token with custom role claim."""
    token = AccessToken.for_user(user)
    
    # Add custom claims
    token['username'] = user.username
    token['role'] = getattr(user, 'role', 'user')
    token['email'] = getattr(user, 'email', '')
    
    return str(token)


# ======================================================
# DASHBOARD
# ======================================================

@login_required
def dashboard(request):
    """Dashboard that loads session, token, widgets."""
    # Create token with role included
    token = create_token_with_role(request.user)
    request.session['access_jwt'] = token

    requested = request.GET.get("session_id")
    if requested:
        try:
            session = ChatSession.objects.get(id=requested, user=request.user)
        except:
            session = ChatSession.objects.filter(user=request.user).last()
        return render(request, "dashboard.html", {
            "session": session,
            "access_jwt": token,
        })

    # Load or create last session
    session = ChatSession.objects.filter(user=request.user).last()
    if not session:
        session = ChatSession.objects.create(user=request.user, title="New Chat", context={})

    return render(request, "dashboard.html", {
        "session": session,
        "access_jwt": token,
    })


# ======================================================
# JWT Mint
# ======================================================

@login_required
def mint_token(request):
    """Generate JWT with role claim."""
    token = create_token_with_role(request.user)
    request.session["access_jwt"] = token
    
    return JsonResponse({
        "ok": True,
        "token": token,
        "user_id": str(request.user.id),
        "username": request.user.username,
        "role": getattr(request.user, "role", "user"),
    })


# ======================================================
# WHOAMI / RBAC / AUDIT
# ======================================================

@login_required
def whoami(request):
    return JsonResponse({
        "username": request.user.username,
        "role": getattr(request.user, "role", None),
        "id": str(request.user.id),
        "is_authenticated": True,
    })


@login_required
def effective_rbac(request):
    role = getattr(request.user, "role", "")
    matrix = {
        "Admin": {"PHI": "all", "Patients": "all", "Records": "all"},
        "Doctor": {"PHI": "limited", "Patients": "view", "Records": "edit"},
        "Nurse": {"PHI": "redacted", "Patients": "view", "Records": "view"},
        "Auditor": {"PHI": "view", "Patients": "view", "Records": "view"},
        "Billing": {"PHI": "insurance-only"},
    }
    return JsonResponse({"role": role, "effective": matrix.get(role, {})})


@login_required
def audit_latest(request):
    logs = (AuditLog.objects
            .filter(user=request.user)
            .order_by("-timestamp")[:25]
            .values("timestamp", "action", "table_name", "ip_address"))
    return JsonResponse({"items": list(logs)})


# ======================================================
# MCP Proxy
# ======================================================

@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def mcp_proxy(request):
    jwt_token = str(request.auth)
    try:
        payload = json.loads(request.body.decode())
    except:
        return Response({"error": "Invalid JSON"}, status=400)

    try:
        resp = requests.post(
            MCP_URL,
            json=payload,
            headers={"Authorization": f"Bearer {jwt_token}"},
            timeout=20,
        )
    except Exception as e:
        return Response({"error": f"MCP unreachable: {e}"}, status=502)

    try:
        return Response(resp.json(), status=resp.status_code)
    except:
        return Response({"error": resp.text}, status=resp.status_code)


# ======================================================
# CHAT TITLE GENERATION
# ======================================================

def generate_chat_title(first_message):
    """Generate a smart title for chat session based on first message."""
    if not first_message or len(first_message) < 3:
        return "New Chat"
    
    # Quick heuristic titles for common patterns
    message_lower = first_message.lower()
    
    # Patient queries
    if re.search(r'\b[A-Z0-9]{5}\b', first_message):
        match = re.search(r'\b([A-Z0-9]{5})\b', first_message)
        if match:
            patient_id = match.group(1)
            if 'medical' in message_lower or 'record' in message_lower:
                return f"Medical Records: {patient_id}"
            elif 'appointment' in message_lower:
                return f"Appointments: {patient_id}"
            elif 'overview' in message_lower or 'info' in message_lower:
                return f"Patient Info: {patient_id}"
            elif 'phi' in message_lower or 'ssn' in message_lower or 'address' in message_lower:
                return f"PHI Request: {patient_id}"
            elif 'admission' in message_lower:
                return f"Admissions: {patient_id}"
            else:
                return f"Patient {patient_id} Query"
    
    # General queries
    if 'shift' in message_lower or 'schedule' in message_lower:
        return "My Schedule"
    elif 'help' in message_lower or 'how' in message_lower:
        return "Help & Support"
    elif any(word in message_lower for word in ['search', 'find', 'look']):
        return "Patient Search"
    elif 'report' in message_lower or 'summary' in message_lower:
        return "Report Generation"
    
    # Fallback: Use first few words
    words = first_message.split()[:5]
    title = ' '.join(words)
    if len(title) > 40:
        title = title[:40] + "..."
    return title.capitalize()


# ======================================================
# CHAT SESSIONS
# ======================================================

@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def chat_session_create(request):
    """Create a new chat session - always starts empty."""
    data = json.loads(request.body.decode()) if request.body else {}

    title = data.get("title", "New Chat")
    first_message = data.get("first_message")
    
    if first_message:
        title = generate_chat_title(first_message)
    
    session = ChatSession.objects.create(
        user=request.user, 
        title=title, 
        context={}
    )

    try:
        AuditLog.objects.create(
            user=request.user,
            action="CHAT_SESSION_CREATED",
            table_name="ChatSession",
            record_id=session.id,
            ip_address=get_client_ip(request),
        )
    except Exception as e:
        print(f"Audit log failed: {e}")

    return Response({
        "session_id": str(session.id),
        "title": session.title,
        "created_at": session.created_at.isoformat(),
        "messages": [],
    })


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def chat_sessions_list(request):
    sessions = ChatSession.objects.filter(user=request.user).order_by("-updated_at")[:20]
    return Response({
        "sessions": [
            {
                "session_id": str(s.id),
                "title": s.title,
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ]
    })


# ======================================================
# CLASSIC NON-STREAMING CHAT
# ======================================================

@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def chat_message_send(request):
    data = json.loads(request.body.decode())
    session_id = data.get("session_id")
    text = data.get("message")

    session = ChatSession.objects.get(id=session_id, user=request.user)

    ChatMessage.objects.create(session=session, role="user", content=text)

    handler = LLMAgentHandler(request.user, request)
    resp = handler.get_response(text)

    msg = ChatMessage.objects.create(
        session=session,
        role="assistant",
        content=resp.get("content", "")
    )

    return Response({
        "message_id": msg.id,
        "content": msg.content,
        "created_at": msg.created_at.isoformat(),
    })


# ======================================================
# STREAMING WRAPPER (sync -> async)
# ======================================================

def stream_llm_sync(agent, user_message):
    """SYNC generator wrapper around async stream_chat()."""
    import asyncio
    
    loop = None
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    async_gen = agent.stream_chat(user_message)

    while True:
        try:
            chunk = loop.run_until_complete(async_gen.__anext__())
        except StopAsyncIteration:
            break
        yield chunk


# ======================================================
# SSE STREAMING CHAT (FIXED)
# ======================================================

@csrf_exempt
@login_required
def chat_stream(request):
    """Primary SSE endpoint with MCP tool support."""
    if request.method != "GET":
        return StreamingHttpResponse("Method not allowed", status=405)

    session_id = request.GET.get("session_id")
    text = request.GET.get("message")

    if not session_id or not text:
        return HttpResponseBadRequest("Missing session_id or message")

    try:
        session = ChatSession.objects.get(id=session_id, user=request.user)
    except ChatSession.DoesNotExist:
        return HttpResponseBadRequest("Invalid session")
    
    # FIX: Auto-generate title on first message - CORRECTED INDENTATION
    title_updated = False
    if session.title == "New Chat":
        message_count = ChatMessage.objects.filter(session=session).count()
        if message_count == 0:  # This is the first message
            session.title = generate_chat_title(text)
            session.save()
            title_updated = True
            print(f"📝 Auto-titled session: {session.title}")
    
    # Save user message
    ChatMessage.objects.create(session=session, role="user", content=text)

    # FIX: Pass session to agent for context persistence
    agent = StreamingLLMAgent(request.user, request, session)
    
    # Capture title for closure
    current_title = session.title

    def event_stream():
        """Generator that yields SSE-formatted events."""
        try:
            # FIX: Send session title update if it was auto-generated
            if title_updated:
                yield sse("session_update", {"title": current_title})
            
            yield sse("start", {"status": "ok"})

            full_response = ""

            for chunk_json in stream_llm_sync(agent, text):
                try:
                    data = json.loads(chunk_json)

                    if data.get("type") == "message":
                        content = data.get("content", "")
                        full_response += content
                        yield sse("chunk", {"delta": content})

                    elif data.get("type") == "tool_call":
                        yield sse("tool_call", {
                            "tool_name": data.get("tool_name"),
                            "arguments": data.get("arguments")
                        })

                    elif data.get("type") == "tool_result":
                        yield sse("tool_result", {
                            "tool_name": data.get("tool_name"),
                            "success": data.get("success"),
                            "data": data.get("data"),
                            "error": data.get("error"),
                            "is_empty": data.get("is_empty", False)
                        })

                    elif data.get("type") == "error":
                        yield sse("error", {"message": data.get("content")})

                except json.JSONDecodeError as e:
                    print(f"JSON decode error: {e}, chunk: {chunk_json}")
                    continue

            # Save assistant message
            if full_response:
                ChatMessage.objects.create(
                    session=session,
                    role="assistant",
                    content=full_response
                )

            yield sse("end", {"done": True})

        except Exception as e:
            print(f"Error in event_stream: {e}")
            import traceback
            traceback.print_exc()
            yield sse("error", {"message": str(e)})

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# ======================================================
# CHAT HISTORY
# ======================================================

@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def chat_history(request):
    """Get chat history for a session."""
    session_id = request.query_params.get("session_id")
    
    if not session_id:
        return Response({"error": "Missing session_id"}, status=400)
    
    try:
        session = ChatSession.objects.get(id=session_id, user=request.user)
    except ChatSession.DoesNotExist:
        return Response({"error": "Session not found"}, status=404)
    
    msgs = ChatMessage.objects.filter(session=session).order_by("created_at")

    return Response({
        "session_id": str(session.id),
        "title": session.title,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ]
    })


# ======================================================
# SAMPLE DATA API (for dashboard)
# ======================================================

@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def sample_data(request):
    """
    Returns sample patients and staff for the dashboard.
    Used to populate quick-access panels and example queries.
    """
    patients = []
    staff = []
    
    try:
        from ehr.models import Patient
        
        # Get random sample of patients
        patient_qs = Patient.objects.all().order_by('?')[:6]
        for p in patient_qs:
            patients.append({
                "patient_id": p.patient_id,
                "name": f"{p.first_name} {p.last_name}",
                "gender": p.gender,
                "birth_year": str(p.date_of_birth_year) if p.date_of_birth_year else "N/A"
            })
    except Exception as e:
        print(f"Error fetching patients: {e}")
        # Fallback sample patients
        patients = [
            {"patient_id": "FCE57", "name": "Leah Arnold", "gender": "F", "birth_year": "1985"},
            {"patient_id": "6VCB8", "name": "Michael Chen", "gender": "M", "birth_year": "1972"},
        ]
    
    try:
        from ehr.models import Staff
        
        # Get staff with linked users
        staff_qs = Staff.objects.select_related('user').filter(user__isnull=False)[:6]
        for s in staff_qs:
            if s.user:
                staff.append({
                    "staff_id": str(s.staff_id),
                    "name": s.full_name,
                    "username": s.user.username,
                    "role": getattr(s.user, 'role', 'Staff'),
                    "department": s.department or "General"
                })
    except Exception as e:
        print(f"Error fetching staff: {e}")
    
    return Response({
        "patients": patients,
        "staff": staff
    })


# ======================================================
# DEMO ACCOUNTS API (public - for landing/login)
# ======================================================

@api_view(["GET"])
@permission_classes([AllowAny])
def demo_accounts(request):
    """
    Returns demo accounts for the landing and login pages.
    Fetches real users from database.
    """
    accounts = []
    
    try:
        # Try to get demo users
        demo_users = User.objects.filter(
            username__startswith='demo_'
        ).order_by('username')[:10]
        
        if not demo_users.exists():
            # Fallback: get any users with roles
            demo_users = User.objects.filter(
                is_active=True
            ).exclude(
                role__isnull=True
            ).exclude(
                role=''
            ).order_by('?')[:6]
        
        for user in demo_users:
            # Try to get linked staff info
            staff_id = None
            staff_name = user.username
            
            try:
                from ehr.models import Staff
                staff = Staff.objects.filter(user=user).first()
                if staff:
                    staff_id = str(staff.staff_id)
                    staff_name = staff.full_name
            except:
                pass
            
            accounts.append({
                "username": user.username,
                "role": getattr(user, 'role', 'Staff'),
                "name": staff_name,
                "staff_id": staff_id
            })
    
    except Exception as e:
        print(f"Error fetching demo accounts: {e}")
    
    # Always ensure we have some accounts
    if not accounts:
        accounts = [
            {"username": "demo_admin", "role": "Admin", "name": "Admin Demo"},
            {"username": "demo_doctor", "role": "Doctor", "name": "Dr. Demo"},
            {"username": "demo_nurse", "role": "Nurse", "name": "Nurse Demo"},
            {"username": "demo_auditor", "role": "Auditor", "name": "Auditor Demo"},
            {"username": "demo_reception", "role": "Reception", "name": "Reception Demo"},
            {"username": "demo_billing", "role": "Billing", "name": "Billing Demo"},
        ]
    
    return Response({
        "accounts": accounts,
        "default_password": "DemoPass123!"
    })


# ======================================================
# TEST ENDPOINT
# ======================================================

@login_required
def test_openai(request):
    """Test if OpenAI is working"""
    from openai import OpenAI
    
    client = OpenAI(api_key=LLMConfig.OPENAI_KEY)
    
    try:
        response = client.chat.completions.create(
            model=LLMConfig.MODEL,
            messages=[
                {"role": "user", "content": "Say hello in one word"}
            ]
        )
        
        return JsonResponse({
            "success": True,
            "response": response.choices[0].message.content,
            "model": response.model
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        })

# ==========================================
# DEMO DATA IMPORT
# ==========================================

def seed_data_page(request):
    return render(request, 'seed_data.html')

@require_http_methods(["POST"])
def seed_data_run(request):
    # Imports and calls YOUR original seed_demo_data.py functions
    from seed_demo_data import (
    create_staff,
    create_patients,
    create_admissions,
    create_appointments,
    create_records,
    create_shifts,
    create_audits,
    )