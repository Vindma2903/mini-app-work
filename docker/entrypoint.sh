#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] waiting for postgres at ${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}..."
python <<'PY'
import os, socket, time, sys
host = os.getenv("POSTGRES_HOST", "postgres")
port = int(os.getenv("POSTGRES_PORT", "5432"))
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            sys.exit(0)
    except OSError:
        time.sleep(1)
print(f"postgres at {host}:{port} not reachable", file=sys.stderr)
sys.exit(1)
PY

echo "[entrypoint] running migrations..."
python manage.py migrate --noinput

if [ "${RUN_COLLECTSTATIC:-1}" = "1" ]; then
    echo "[entrypoint] collecting static files..."
    python manage.py collectstatic --noinput
fi

exec "$@"
