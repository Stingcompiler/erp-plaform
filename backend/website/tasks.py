"""Nightly rollup of first-party page visits (see website/analytics.py).

Runs from the same schedulers as the other daily jobs: run_daily_scans for
the Render cron / standalone timer, CELERY_BEAT_SCHEDULE for a worker.
"""

from celery import shared_task


@shared_task
def rollup_page_visits():
    from website.analytics import rollup

    return rollup()
