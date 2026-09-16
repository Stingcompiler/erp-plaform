"""When a user last signed in and when they were last seen using the app.

`last_login` is Django's field, but our JWT LoginView never called
`django.contrib.auth.login()`, so the `user_logged_in` signal that fills it
never fired and every account read "never signed in". `record_login` fills
it now. `last_seen_at` is ours: the cookie authentication touches it on
authenticated requests, at most once per TOUCH_INTERVAL per user, so a
member counts as online while the app keeps talking to the API and drops
off ONLINE_WINDOW after their last request — without a write per request
and without a heartbeat from the browser.
"""
from datetime import timedelta

from django.contrib.auth.models import update_last_login
from django.utils import timezone

# A member is "online" when seen within this window …
ONLINE_WINDOW = timedelta(minutes=5)
# … and the row is written at most this often while they keep working.
TOUCH_INTERVAL = timedelta(minutes=2)


def touch_last_seen(user, *, force=False, now=None):
    """Record that `user` is using the app now. Returns True when a row was
    written; skipped (False) when the last touch is recent enough."""
    now = now or timezone.now()
    last = getattr(user, "last_seen_at", None)
    if not force and last is not None and now - last < TOUCH_INTERVAL:
        return False
    type(user).objects.filter(pk=user.pk).update(last_seen_at=now)
    user.last_seen_at = now
    return True


def record_login(user):
    """Sign-in: Django's last_login plus a forced presence touch."""
    update_last_login(None, user)
    touch_last_seen(user, force=True)


def is_online(user, now=None):
    last = getattr(user, "last_seen_at", None)
    return bool(last) and (now or timezone.now()) - last < ONLINE_WINDOW
