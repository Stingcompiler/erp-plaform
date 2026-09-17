"""Run the daily scans in-process, for a Render Cron Job.

The scans are Celery tasks, but a worker plus a Redis broker is two extra
paid services for three jobs that run once a day. Calling the task
functions directly from a cron job gives the same audit rows with nothing
to keep alive between runs. If a worker is ever deployed, CELERY_BEAT_SCHEDULE
already covers these; run one or the other, not both.
"""

import json

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the daily receivables, stock and subscription scans synchronously."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=["receivables", "stock", "subscriptions", "activity_archive", "analytics"],
            help="Run a single scan instead of all three.",
        )

    def handle(self, *args, **options):
        from core.tasks import archive_activity_logs
        from website.tasks import rollup_page_visits
        from inventory.tasks import scan_stock_alerts
        from sales.tasks import scan_due_receivables
        from subscriptions.tasks import scan_subscription_expiries

        scans = {
            "receivables": scan_due_receivables,
            "stock": scan_stock_alerts,
            "subscriptions": scan_subscription_expiries,
            # Not a scan, but it belongs on the same nightly cadence and
            # this command is what the cron and the standalone timer run.
            "activity_archive": archive_activity_logs,
            "analytics": rollup_page_visits,
        }
        chosen = [options["only"]] if options.get("only") else list(scans)
        results = {}
        failures = 0
        for name in chosen:
            try:
                # .run() executes the task body here, bypassing the broker.
                results[name] = scans[name].run()
                self.stdout.write(f"{name}: ok")
            except Exception as exc:  # noqa: BLE001 - one failing scan must not hide the others
                failures += 1
                results[name] = {"error": str(exc)}
                self.stderr.write(f"{name}: FAILED {exc}")
        self.stdout.write(json.dumps(results, default=str))
        if failures:
            raise SystemExit(1)
