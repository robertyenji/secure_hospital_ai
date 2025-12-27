# mcp_server/security.py
"""
Security utilities for the FastAPI MCP gateway.

- Validates Authorization: Bearer <JWT>
- Verifies signature, expiry, (optional) issuer/audience
- Loads the Django user and returns a principal dict {user_id, username, role}

Set env:
  JWT_ALG=HS256 (default) or RS256
  JWT_SECRET=<shared secret>        # for HS256
  JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"  # for RS256
  JWT_ISSUER=<optional>             # e.g. "secure-hospital-django"
  JWT_AUDIENCE=<optional>           # e.g. "mcp-gateway"
"""

import os
from typing import Dict, Any, Optional
from fastapi import Header, HTTPException, status, Depends

import jwt  # PyJWT
from jwt import InvalidTokenError, ExpiredSignatureError, InvalidSignatureError

from django.contrib.auth import get_user_model

JWT_ALG = os.getenv("JWT_ALG", "HS256").upper()
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_PUBLIC_KEY = os.getenv("JWT_PUBLIC_KEY", "")
JWT_ISSUER = os.getenv("JWT_ISSUER", None)
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", None)

User = get_user_model()


def _decode_jwt(token: str) -> Dict[str, Any]:
    """Decode and verify a JWT using configured algorithm."""
    kwargs: Dict[str, Any] = {"algorithms": [JWT_ALG]}
    if JWT_ISSUER:
        kwargs["issuer"] = JWT_ISSUER
    if JWT_AUDIENCE:
        kwargs["audience"] = JWT_AUDIENCE

    try:
        if JWT_ALG == "RS256":
            if not JWT_PUBLIC_KEY:
                raise HTTPException(status_code=500, detail="JWT_PUBLIC_KEY not set for RS256")
            return jwt.decode(token, JWT_PUBLIC_KEY, **kwargs)
        # HS256 default
        if not JWT_SECRET:
            raise HTTPException(status_code=500, detail="JWT_SECRET not set for HS256")
        return jwt.decode(token, JWT_SECRET, **kwargs)
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT expired")
    except (InvalidSignatureError, InvalidTokenError) as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid JWT: {str(e)}")


def _get_user_from_claims(claims: Dict[str, Any]) -> Optional[User]:
    """
    Map token claims to a Django User.
    Supports `user_id` (preferred) or `sub` as a fallback.
    """
    user_id = claims.get("user_id") or claims.get("sub")
    if not user_id:
        return None
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None


def get_current_principal(authorization: str = Header(None)) -> Dict[str, Any]:
    """
    FastAPI dependency:
      - Parses `Authorization: Bearer <token>`
      - Validates JWT
      - Loads Django User
      - Returns {user_id, username, role}
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")

    token = authorization.split(" ", 1)[1].strip()
    claims = _decode_jwt(token)
    user = _get_user_from_claims(claims)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found for token")

    # You store role on the user model (audit.User.role)
    role = getattr(user, "role", None) or claims.get("role")
    if not role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User has no role assigned")

    return {
        "user_id": str(user.pk),
        "username": user.username,
        "role": str(role),
        "user_obj": user,  # handy for audit
    }
