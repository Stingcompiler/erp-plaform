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
workers = int(os.environ.get("WEB_CONCURRENCY", multiprocessing.cpu_count() * 2 + 1))
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
