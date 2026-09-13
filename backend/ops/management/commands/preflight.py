from django.core.management.base import BaseCommand, CommandError

from ops import preflight


class Command(BaseCommand):
    """
    Run pre-install / pre-upgrade checks and report each as ok/warn/fail.

    Exits non-zero only when a check FAILS. Warnings are printed but do not
    block, so an operator can still see the whole picture on a first install.
    """

    help = "Check deployment readiness before installing or upgrading."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the findings as JSON (for automation).",
        )

    def handle(self, *args, **options):
        findings = preflight.run_preflight()

        if options["json"]:
            import json as json_module

            self.stdout.write(
                json_module.dumps([finding.as_dict() for finding in findings], indent=2)
            )
        else:
            symbols = {preflight.OK: "ok  ", preflight.WARN: "warn", preflight.FAIL: "FAIL"}
            for finding in findings:
                style = {
                    preflight.OK: self.style.SUCCESS,
                    preflight.WARN: self.style.WARNING,
                    preflight.FAIL: self.style.ERROR,
                }[finding.level]
                self.stdout.write(
                    f"[{symbols[finding.level]}] {finding.code:18} {style(finding.detail)}"
                )

        blocking = [finding for finding in findings if finding.is_blocking]
        if blocking:
            raise CommandError(
                f"{len(blocking)} blocking issue(s); resolve them before proceeding."
            )
        self.stdout.write(self.style.SUCCESS("Preflight passed with no blocking issues."))
