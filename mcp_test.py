"""
MCP Server Standalone Test Suite
--------------------------------
This version tests ONLY the MCP server without Django login.

Usage:
    python test_mcp_tools.py

.env requirements:
    MCP_URL=http://localhost:9000
    JWT_SECRET=your_secret
    JWT_ALG=HS256
    TEST_PATIENT_ID=NUGWI
    TEST_STAFF_ID=STAFF-001

Make sure MCP server is running:
    uvicorn mcp_server.main:app --host 127.0.0.1 --port 9000 --reload
"""

import os
import json
import jwt
import requests
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime

# ============================
# Load .env from project root
# ============================
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / ".env"
load_dotenv(env_path)

# ============================
# Configuration
# ============================
MCP_URL = os.getenv("MCP_URL", "http://localhost:9000")
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALG = os.getenv("JWT_ALG", "HS256")
TEST_PATIENT_ID = os.getenv("TEST_PATIENT_ID", "john.cobb@hospital.com")
TEST_STAFF_ID = os.getenv("TEST_STAFF_ID", "CTEXO")

# ============================
# Terminal Colors
# ============================
class Colors:
    OK = "\033[92m"
    FAIL = "\033[91m"
    INFO = "\033[96m"
    HDR = "\033[95m"
    END = "\033[0m"
    BOLD = "\033[1m"


# ============================
# Helper functions
# ============================
def header(text: str):
    print(f"\n{Colors.HDR}{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.HDR}{Colors.BOLD}{text:^60}{Colors.END}")
    print(f"{Colors.HDR}{Colors.BOLD}{'='*60}{Colors.END}\n")


def print_json(data, title="Response"):
    print(f"{Colors.INFO}{title}:{Colors.END}")
    print(json.dumps(data, indent=2, default=str))


# ============================
# Generate a JWT for testing
# ============================
def create_test_jwt():
    payload = {
        "user_id": 1,      # MUST exist in your Django DB
        "username": "mcp_test_user",
        "role": "doctor"
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


JWT_TOKEN = create_test_jwt()


# ============================
# MCP CALLER
# ============================
def call_mcp_tool(tool: str, args: dict):
    url = f"{MCP_URL}/mcp/"

    headers = {
        "Authorization": f"Bearer {JWT_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools.call",
        "params": {
            "name": tool,
            "arguments": args,
        }
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        print(f"{Colors.FAIL}❌ MCP Connection Error: {e}{Colors.END}")
        return None

    try:
        return resp.status_code, resp.json()
    except:
        return resp.status_code, resp.text


# ============================
# Tests
# ============================
def test_patient_overview():
    header("Test: Patient Overview")
    status, result = call_mcp_tool("get_patient_overview", {"patient_id": TEST_PATIENT_ID})

    print("Status:", status)
    print_json(result)
    return status == 200


def test_admissions():
    header("Test: Patient Admissions")
    status, result = call_mcp_tool("get_admissions", {"patient_id": TEST_PATIENT_ID})

    print("Status:", status)
    print_json(result)
    return status == 200


def test_appointments():
    header("Test: Patient Appointments")
    status, result = call_mcp_tool("get_appointments", {"patient_id": TEST_PATIENT_ID})

    print("Status:", status)
    print_json(result)
    return status == 200


def test_medical_records():
    header("Test: Medical Records")
    status, result = call_mcp_tool("get_medical_records", {"patient_id": TEST_PATIENT_ID})

    print("Status:", status)
    print_json(result)
    return status == 200


def test_shifts():
    header("Test: Staff Shifts")
    status, result = call_mcp_tool("get_shifts", {"staff_id": TEST_STAFF_ID})

    print("Status:", status)
    print_json(result)
    return status == 200


def test_invalid_tool():
    header("Test: Invalid Tool Handling")

    status, result = call_mcp_tool("nonexistent_tool", {})

    print("Status:", status)
    print_json(result)

    return status == 200 and "Unknown tool" in str(result)


# ============================
# Run All Tests
# ============================
def run_tests():
    header("MCP Server Standalone Tests")
    print(f"Time: {datetime.now()}")
    print(f"MCP URL: {MCP_URL}")
    print(f"Using Test JWT (first 40 chars): {JWT_TOKEN[:40]}...\n")

    tests = [
        ("Patient Overview", test_patient_overview),
        ("Admissions", test_admissions),
        ("Appointments", test_appointments),
        ("Medical Records", test_medical_records),
        ("Staff Shifts", test_shifts),
        ("Invalid Tool", test_invalid_tool),
    ]

    results = []
    for name, func in tests:
        try:
            ok = func()
            results.append((name, ok))
        except Exception as e:
            print(f"{Colors.FAIL}🔥 Test crashed: {e}{Colors.END}")
            results.append((name, False))

    # Summary
    header("Test Summary")
    for name, ok in results:
        status = f"{Colors.OK}PASS{Colors.END}" if ok else f"{Colors.FAIL}FAIL{Colors.END}"
        print(f"{status} - {name}")

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.END}")


if __name__ == "__main__":
    run_tests()
