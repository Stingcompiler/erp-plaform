"""
pytest configuration for the backend test suite.

The login rate throttle (M10) records attempt history in Django's cache, which
is one in-process LocMemCache shared across the whole test run. We clear it
before every test so throttle state can't bleed from one test into the next and
spuriously return 429. A runtest hook is used (rather than an autouse fixture)
so it reliably runs for unittest-style APITestCase tests too.
"""


def pytest_runtest_setup(item):
    from django.core.cache import cache
    cache.clear()
