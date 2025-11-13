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
    
    # Chat API endpoints
    path("api/chat/session/", views.chat_session_create, name="chat_session_create"),
    path("api/chat/sessions/", views.chat_sessions_list, name="chat_sessions_list"),
    path("api/chat/message/", views.chat_message_send, name="chat_message_send"),
    path("api/chat/history/", views.chat_history, name="chat_history"),
]
