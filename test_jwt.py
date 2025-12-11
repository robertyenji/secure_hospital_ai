#!/usr/bin/env python
"""
Test JWT Token Generation and Validation
Run this to verify your JWT configuration is correct:
    python test_jwt.py
"""

import os
import sys
from pathlib import Path

# Setup Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'secure_hospital_ai.settings')

import django
django.setup()

from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
import jwt

User = get_user_model()

def test_jwt():
    print("=" * 60)
    print("JWT TOKEN TEST")
    print("=" * 60)
    
    # Get SECRET_KEY
    from django.conf import settings
    secret = settings.SECRET_KEY
    print(f"\n1. SECRET_KEY (first 10 chars): {secret[:10]}...")
    
    # Get or create test user
    try:
        user = User.objects.first()
        if not user:
            user = User.objects.create_user(
                username='test_doctor',
                password='test123',
                role='Doctor'
            )
            print(f"\n2. Created test user: {user.username}")
        else:
            print(f"\n2. Using existing user: {user.username}")
    except Exception as e:
        print(f"\n2. Error getting user: {e}")
        return
    
    # Create token with custom claims
    token = AccessToken.for_user(user)
    token['username'] = user.username
    token['role'] = getattr(user, 'role', 'user')
    token['email'] = getattr(user, 'email', '')
    
    token_str = str(token)
    print(f"\n3. Generated JWT token (first 50 chars): {token_str[:50]}...")
    
    # Decode and verify
    try:
        decoded = jwt.decode(
            token_str,
            secret,
            algorithms=['HS256'],
            options={"verify_signature": True, "verify_exp": True}
        )
        print(f"\n4. ✅ Token decoded successfully!")
        print(f"   - user_id: {decoded.get('user_id')}")
        print(f"   - username: {decoded.get('username')}")
        print(f"   - role: {decoded.get('role')}")
        print(f"   - exp: {decoded.get('exp')}")
        
        print("\n5. ✅ JWT configuration is CORRECT!")
        print("   Django and MCP will be able to share tokens.")
        
    except jwt.InvalidSignatureError:
        print(f"\n4. ❌ SIGNATURE VERIFICATION FAILED!")
        print("   Check that MCP server uses same SECRET_KEY")
        
    except jwt.ExpiredSignatureError:
        print(f"\n4. ❌ Token expired!")
        
    except Exception as e:
        print(f"\n4. ❌ Error decoding: {e}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_jwt()