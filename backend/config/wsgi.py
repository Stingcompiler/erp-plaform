"""
WSGI config for the ERP backend. Exposes the WSGI callable as a module-level
variable named ``application``, served in production by Gunicorn:

    gunicorn config.wsgi:application
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
