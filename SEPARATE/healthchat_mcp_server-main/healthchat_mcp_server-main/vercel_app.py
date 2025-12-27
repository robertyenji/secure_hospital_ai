# mcp_server/vercel_app.py
"""
Vercel-compatible wrapper for MCP FastAPI server - STANDALONE
No Django dependencies required.
"""

# Import the FastAPI app
from main import app

# Vercel expects the app to be named 'app' or 'handler'
handler = app
