import json
import requests

MCP_SERVER_URL = "http://127.0.0.1:9000/mcp/"
TOOL_NAME = "get_secure_patient_data"
TEST_PATIENT_ID = "J51AR"

def call_mcp_tool(tool_name: str, arguments: dict):
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools.call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        print(f"\n➡️ Sending request to {MCP_SERVER_URL} ...")
        print(json.dumps(payload, indent=2))

        resp = requests.post(MCP_SERVER_URL, json=payload, timeout=10)
        print(f"⬅️ Status code: {resp.status_code}")
        print(f"⬅️ Response text: {resp.text[:300]}")  # first 300 chars
        resp.raise_for_status()
        return resp.json()

    except Exception as e:
        print(f"❌ Error calling MCP server: {e}")
        return None

def main():
    result = call_mcp_tool(TOOL_NAME, {"patient_id": TEST_PATIENT_ID})
    if result:
        print("\n✅ MCP Response:")
        print(json.dumps(result, indent=2))
    else:
        print("⚠️ No response received from MCP server.")

if __name__ == "__main__":
    main()
