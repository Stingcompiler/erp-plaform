"""
ASGI config for the ERP backend. Not used by the Render deployment (which
runs Gunicorn/WSGI per PROJECT_RULES), but kept so Django's own tooling
(e.g. `runserver`, future websocket needs) has a valid entrypoint.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
