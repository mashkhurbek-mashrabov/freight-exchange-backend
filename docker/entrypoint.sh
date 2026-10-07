#!/bin/sh
set -e

# Wait for database connection
if [ "${SKIP_DB_WAIT:-0}" != "1" ]; then
    python - << 'EOF'
import os
import socket
import sys
import time
from urllib.parse import urlparse

db_url = os.environ.get("DATABASE_URL", "")
if db_url:
    parsed = urlparse(db_url)
    host = parsed.hostname or "db"
    port = parsed.port or 5432
else:
    host = os.environ.get("POSTGRES_HOST", "db")
    port = int(os.environ.get("POSTGRES_PORT", "5432"))

timeout = int(os.environ.get("DB_WAIT_TIMEOUT", "60"))
start = time.time()
print(f"Waiting for database at {host}:{port}...", flush=True)

while True:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"Database at {host}:{port} is ready.", flush=True)
            break
    except OSError:
        if time.time() - start > timeout:
            print(f"Timed out waiting for database at {host}:{port}.", file=sys.stderr, flush=True)
            sys.exit(1)
        time.sleep(1)
EOF
fi

if [ "${RUN_MIGRATIONS:-0}" = "1" ] || [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "Running database migrations..."
    python manage.py migrate --noinput

    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

exec "$@"
