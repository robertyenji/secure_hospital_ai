# mcp_server/auth_middleware.py
"""
JWT AUTH MIDDLEWARE FOR MCP SERVER
-----------------------------------
Validates JWT tokens from Django and extracts user information.
Must use the SAME secret as Django's simplejwt configuration.
"""

import jwt
import os
from fastapi import Request, HTTPException
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
load_dotenv(env_path)

# CRITICAL: Must match Django's SIMPLE_JWT settings
# Django simplejwt uses settings.SECRET_KEY by default
JWT_SECRET = os.getenv("SECRET_KEY")
JWT_ALG = "HS256"  # Django simplejwt default

if not JWT_SECRET:
    raise RuntimeError("SECRET_KEY not found in environment! Check your .env file.")

print(f"🔑 MCP Server using JWT_SECRET (first 10 chars): {JWT_SECRET[:10]}...")


class AuthUser:
    """User object extracted from JWT."""
    def __init__(self, user_id, username="unknown", role="user"):
        self.id = user_id
        self.username = username
        self.role = role

    def __str__(self):
        return f"<AuthUser id={self.id} username={self.username} role={self.role}>"


async def auth_middleware(request: Request, call_next):
    """
    Extract and validate JWT token.
    Attach user info to request.state for use in route handlers.
    """
    
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # Extract token
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")
    
    token = auth_header[7:]  # Remove "Bearer "

    try:
        # Decode JWT using same secret as Django
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALG],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "require": ["user_id", "exp"]
            }
        )

        # Extract user info from token
        user_id = payload.get("user_id")
        
        # Django simplejwt stores username in different ways
        username = (
            payload.get("username") or 
            payload.get("email") or 
            payload.get("sub") or 
            f"user_{user_id}"
        )
        
        # Role might be custom claim you added
        role = payload.get("role", "user")

        # Create user object
        user = AuthUser(user_id=user_id, username=username, role=role)

        # Attach to request
        request.state.user = user
        request.state.role = role
        request.state.username = username
        request.state.user_id = user_id

        print(f"✅ Authenticated: {username} (role: {role}, id: {user_id})")

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="JWT token has expired")
    
    except jwt.InvalidSignatureError:
        print(f"❌ Invalid JWT signature. Check SECRET_KEY matches Django settings.")
        print(f"   Token preview: {token[:20]}...")
        raise HTTPException(status_code=401, detail="Invalid JWT signature")
    
    except jwt.DecodeError as e:
        print(f"❌ JWT decode error: {e}")
        raise HTTPException(status_code=401, detail=f"JWT decode error: {str(e)}")
    
    except Exception as e:
        print(f"❌ Auth error: {e}")
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")

    return await call_next(request)