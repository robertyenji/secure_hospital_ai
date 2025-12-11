# mcp_server/vercel_app.py
"""
Vercel-compatible wrapper for MCP FastAPI server.
This file adapts the FastAPI app for Vercel's serverless environment.
"""

import os
import sys
from pathlib import Path

# Setup paths for Vercel
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Set Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "secure_hospital_ai.settings_prod")

# Initialize Django BEFORE importing anything else
import django
django.setup()

# Now import the FastAPI app from main.py
from mcp_server.main import app

# Vercel expects the app to be named 'app' or 'handler'
# FastAPI is ASGI-compatible, so Vercel can run it directly
handler = app