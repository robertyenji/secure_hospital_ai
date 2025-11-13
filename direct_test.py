import psycopg2

# Try direct connection parameters
params = {
    'host': 'hp001.postgres.database.azure.com',     # PGHOST
    'user': 'robert',                                # PGUSER
    'password': 'Darissa@2023',                      # PGPASSWORD
    'dbname': 'hopital-001',                         # PGDATABASE
    'port': '5432',                                  # PGPORT
    'sslmode': 'require',
    'connect_timeout': 10
}

print("Attempting direct connection with parameters:")
print(f"Host: {params['host']}")
print(f"User: {params['user']}")
print(f"Database: {params['dbname']}")
print(f"Port: {params['port']}")
print(f"SSL Mode: {params['sslmode']}")

try:
    conn = psycopg2.connect(**params)
    print("\n✓ Successfully connected!")
    
    # Try a simple query
    cur = conn.cursor()
    cur.execute('SELECT version()')
    ver = cur.fetchone()
    print(f"\nServer version:\n{ver[0]}")
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"\n✗ Connection failed: {str(e)}")