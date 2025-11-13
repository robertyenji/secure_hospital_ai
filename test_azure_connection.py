import socket
import ssl
import psycopg2
from dotenv import load_dotenv
import os

def test_dns():
    try:
        print("\nTesting DNS resolution...")
        ip = socket.gethostbyname('hp001.postgres.database.azure.com')
        print(f"✓ DNS Resolution successful: {ip}")
    except Exception as e:
        print(f"✗ DNS Resolution failed: {str(e)}")

def test_port():
    try:
        print("\nTesting TCP connection to port 5432...")
        sock = socket.create_connection(('hp001.postgres.database.azure.com', 5432), timeout=10)
        print("✓ TCP connection successful")
        sock.close()
    except Exception as e:
        print(f"✗ TCP connection failed: {str(e)}")

def test_ssl():
    try:
        print("\nTesting SSL connection...")
        context = ssl.create_default_context()
        with socket.create_connection(('hp001.postgres.database.azure.com', 5432)) as sock:
            with context.wrap_socket(sock, server_hostname='hp001.postgres.database.azure.com') as ssock:
                print(f"✓ SSL connection successful (Protocol: {ssock.version()})")
    except Exception as e:
        print(f"✗ SSL connection failed: {str(e)}")

def test_postgres():
    load_dotenv()
    
    print("\nTesting PostgreSQL connection...")
    print(f"Using host: hp001.postgres.database.azure.com")
    print(f"Using database: {os.getenv('PGDATABASE')}")
    print(f"Using username: {os.getenv('PGUSER')}")
    print(f"Client IP (should be allowed in firewall): 97.145.3.219")
    
    try:
        conn = psycopg2.connect(
            host=os.getenv('PGHOST'),
            dbname=os.getenv('PGDATABASE'),
            user=os.getenv('PGUSER'),
            password=os.getenv('PGPASSWORD'),
            port=os.getenv('PGPORT', '5432'),
            sslmode='require',
            connect_timeout=10
        )
        print("✓ PostgreSQL connection successful!")
        
        # Test a simple query
        cur = conn.cursor()
        cur.execute('SELECT version();')
        version = cur.fetchone()[0]
        print(f"\nServer version:\n{version}")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"✗ PostgreSQL connection failed: {str(e)}")

if __name__ == '__main__':
    print("Running comprehensive Azure PostgreSQL connection tests...")
    test_dns()
    test_port()
    test_ssl()
    test_postgres()