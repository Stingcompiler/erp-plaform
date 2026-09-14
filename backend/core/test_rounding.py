import threading
from decimal import Decimal

from django.test import SimpleTestCase


class MoneyRoundingTests(SimpleTestCase):
    """Half-up is the contract for every money figure; it must hold on the
    request thread and on any thread Django or Celery spawns later."""

    def test_half_up_on_current_thread(self):
        self.assertEqual(Decimal("0.125").quantize(Decimal("0.01")), Decimal("0.13"))
        self.assertEqual(Decimal("2.675").quantize(Decimal("0.01")), Decimal("2.68"))

    def test_half_up_on_a_new_thread(self):
        seen = {}

        def work():
            seen["value"] = Decimal("0.125").quantize(Decimal("0.01"))

        thread = threading.Thread(target=work)
        thread.start()
        thread.join()
        self.assertEqual(seen["value"], Decimal("0.13"))

    def test_pos_tax_uses_half_up(self):
        from tax.handlers import TaxHandler

        class Profile:
            flat_tax_rate = Decimal("15")

        # 0.83 * 15% = 0.1245 -> 0.12 either way; 0.85 * 15% = 0.1275 -> 0.13 half-up
        self.assertEqual(TaxHandler(Profile()).compute_tax("0.85"), Decimal("0.13"))
