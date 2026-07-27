"""
Celery app for the ERP backend, run in production as the `erp-worker`
Render Background Worker (see render.yaml). Tasks are added per-app as
milestones need them (e.g. M7 sync processing, M9 report generation,
M10 scheduled backups run via erp-backup-cron instead).
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("erp_backend")

# Read CELERY_* settings from Django settings.py (see config/settings.py).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in every installed app.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
