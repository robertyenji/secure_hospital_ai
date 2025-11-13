import os
from dotenv import load_dotenv
import psycopg2
from urllib.parse import urlparse

# Load environment variables from .env
load_dotenv()

# Get DATABASE_URL
db_url = os.getenv('DATABASE_URL')
print(f"\nTesting connection using DATABASE_URL:")
print(f"DATABASE_URL (censored) = {db_url.replace(db_url.split(':')[2].split('@')[0], '***HIDDEN***')}")

# Parse the URL to show components
url = urlparse(db_url)
print(f"\nParsed connection details:")
print(f"Username: {url.username}")  # Should be 'robert@hp001'
print(f"Host: {url.hostname}")      # Should be 'hp001.postgres.database.azure.com'
print(f"Port: {url.port}")          # Should be 5432
print(f"Database: {url.path[1:]}")  # Should be 'postgres'

print("\nAttempting connection...")
try:
    conn = psycopg2.connect(db_url, sslmode='require')
    print("✓ Successfully connected to database!")
    conn.close()
except Exception as e:
    print(f"✗ Connection failed: {str(e)}")

# Also try with individual PG* vars
print("\nAlternative: Testing with PG* variables:")
print(f"PGUSER: {os.getenv('PGUSER')}")
print(f"PGHOST: {os.getenv('PGHOST')}")
print(f"PGDATABASE: {os.getenv('PGDATABASE')}")
print(f"PGPORT: {os.getenv('PGPORT')}")

try:
    conn = psycopg2.connect(
        host=os.getenv('PGHOST'),
        user=os.getenv('PGUSER'),
        password=os.getenv('PGPASSWORD'),
        dbname=os.getenv('PGDATABASE'),
        port=os.getenv('PGPORT'),
        sslmode='require'
    )
    print("✓ Successfully connected using PG* variables!")
    conn.close()
except Exception as e:
    print(f"✗ Connection failed using PG* variables: {str(e)}")