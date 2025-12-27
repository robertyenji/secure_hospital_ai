# frontend/urls.py
"""
URL configuration for frontend app.
Includes:
- Main views (landing, login, dashboard, chat)
- Documentation pages (docs, API reference)
- Legal pages (privacy, terms, disclaimer)
- API endpoints (sample data, demo accounts, chat, etc.)
"""

from django.urls import path
from . import views

app_name = 'frontend'

urlpatterns = [
    # ==========================================
    # MAIN PAGES
    # ==========================================
    path('', views.landing_page, name='landing'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),  # Custom logout with audit
    path('chat/', views.dashboard, name='dashboard'),
    
    # ==========================================
    # DOCUMENTATION PAGES
    # ==========================================
    path('docs/', views.documentation, name='documentation'),
    path('api-reference/', views.api_reference, name='api_reference'),
    
    # ==========================================
    # LEGAL PAGES
    # ==========================================
    path('privacy/', views.privacy_policy, name='privacy_policy'),
    path('terms/', views.terms_of_service, name='terms_of_service'),
    path('disclaimer/', views.disclaimer, name='disclaimer'),
    
    # ==========================================
    # AUTH / USER APIs
    # ==========================================
    path('whoami/', views.whoami, name='whoami'),
    path('mint-token/', views.mint_token, name='mint_token'),
    path('effective-rbac/', views.effective_rbac, name='effective_rbac'),
    path('audit-latest/', views.audit_latest, name='audit_latest'),
    
    # ==========================================
    # RBAC APIs
    # ==========================================
    path('api/rbac/', views.rbac_matrix, name='rbac_matrix'),
    path('api/my-permissions/', views.my_permissions, name='my_permissions'),
    
    # ==========================================
    # MCP PROXY
    # ==========================================
    path('mcp/', views.mcp_proxy, name='mcp_proxy'),
    
    # ==========================================
    # CHAT APIs (using original function names)
    # ==========================================
    path('api/chat/session/', views.chat_session_create, name='chat_session_create'),
    path('api/chat/sessions/', views.chat_sessions_list, name='chat_sessions_list'),
    path('api/chat/history/', views.chat_history, name='chat_history'),
    path('api/chat/message/', views.chat_message_send, name='chat_message_send'),
    path('chat/stream/', views.chat_stream, name='chat_stream'),
    
    # ==========================================
    # SAMPLE DATA & DEMO ACCOUNTS APIs
    # ==========================================
    path('api/sample-data/', views.sample_data, name='sample_data'),
    path('api/demo-accounts/', views.demo_accounts, name='demo_accounts'),

    # ==========================================
    # DEMO DATA IMPORT
    # ==========================================
    path('seed-data/', views.seed_data_page, name='seed_data_page'),
    path('seed-data/run/', views.seed_data_run, name='seed_data_run'),
        
    # ==========================================
    # TEST ENDPOINTS
    # ==========================================
    path('test-openai/', views.test_openai, name='test_openai'),
]