# mcp_server/auth_middleware.py
"""
JWT AUTH MIDDLEWARE FOR MCP SERVER - STANDALONE
------------------------------------------------
Validates JWT tokens and extracts user information.
No Django dependencies - pure JWT validation.
"""

import os
import jwt
from fastapi import Request, HTTPException
from dotenv import load_dotenv

load_dotenv()

# JWT Configuration - use SECRET_KEY to match Django
JWT_SECRET = os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
JWT_PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY", "")

if not JWT_SECRET and JWT_ALG == "HS256":
    raise RuntimeError("SECRET_KEY not found in environment! Check your .env file.")


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

    Allows unauthenticated access to /health endpoint.
    """

    # Allow health checks without auth
    if request.url.path in ["/health", "/tools", "/rbac", "/docs", "/openapi.json"]:
        return await call_next(request)

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # Extract token
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header format")

    token = auth_header[7:]  # Remove "Bearer "

    try:
        # Decode JWT
        decode_key = JWT_PUBLIC_KEY if JWT_ALG == "RS256" else JWT_SECRET

        payload = jwt.decode(
            token,
            decode_key,
            algorithms=[JWT_ALG],
            options={
                "verify_signature": True,
                "verify_exp": True,
                "require": ["user_id", "exp"]  # Your Django app sends "user_id", not "sub"
            }
        )

        # Extract user info from token
        user_id = payload.get("user_id")

        # Username from various possible claims
        username = (
            payload.get("username") or
            payload.get("email") or
            payload.get("sub") or
            f"user_{user_id}"
        )

        # Role from token
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
