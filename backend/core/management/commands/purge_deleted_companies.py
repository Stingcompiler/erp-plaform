"""Permanently delete companies whose 30-day deletion window has passed.

Normally run by the nightly ``run_daily_scans`` (step ``purge_companies``);
this command runs the same step on its own, e.g. by hand after a failure.
"""

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Purge companies scheduled for deletion whose purge date has passed."

    def handle(self, *args, **options):
        from subscriptions.company_deletion import purge_due

        result = purge_due()
        self.stdout.write(json.dumps(result, default=str))
        if result["failed"]:
            raise SystemExit(1)
