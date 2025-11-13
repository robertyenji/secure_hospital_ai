from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent
dotenv_path = BASE_DIR / ".env"

print("[DEBUG] Looking for:", dotenv_path)
if dotenv_path.exists():
    print("[DEBUG] Found .env file ✅")
    load_dotenv(dotenv_path)
else:
    print("[ERROR] .env file not found ❌")

print("[DEBUG] Loaded Variables:")
for key in ['PGUSER', 'PGPASSWORD', 'PGHOST', 'PGDATABASE']:
    print(f"{key} =", os.getenv(key))
