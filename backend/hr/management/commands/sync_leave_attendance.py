from django.core.management.base import BaseCommand

from hr.leave_sync import sync_approved_leave_attendance


class Command(BaseCommand):
    help = "Create attendance entries for approved leave and refresh employee leave status."

    def handle(self, *args, **options):
        sync_approved_leave_attendance()
        self.stdout.write(self.style.SUCCESS("Approved leave attendance is synchronized."))
