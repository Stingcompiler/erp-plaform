"""
Gunicorn config for the erp-api service (M12).

Used by Render's start command: `gunicorn config.wsgi:application -c gunicorn.conf.py`.
Worker count scales with the container's CPU allotment; tune WEB_CONCURRENCY on
the service if the plan changes.
"""

import multiprocessing
import os

# Render provides $PORT; bind to it (fallback for local runs).
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# 2*CPU+1 is the standard sync-worker heuristic; overridable via WEB_CONCURRENCY.
# Default capped at 3: the container reports the HOST's CPU count (8 on
# Render's starter instance), so the classic 2n+1 formula started 17 sync
# Django processes and blew the 512 MiB limit. Set WEB_CONCURRENCY to size
# it for the instance you actually pay for.
workers = int(os.environ.get("WEB_CONCURRENCY", min(3, multiprocessing.cpu_count() * 2 + 1)))
worker_class = "sync"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
keepalive = 5

# Recycle workers periodically to bound memory growth.
max_requests = 1000
max_requests_jitter = 100

accesslog = "-"   # stdout
errorlog = "-"    # stderr
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
