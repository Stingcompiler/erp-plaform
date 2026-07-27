# Celery app is imported here so it's loaded when Django starts,
# ensuring shared_task decorators use this app.
from .celery import app as celery_app

__all__ = ("celery_app",)
