from django.conf import settings


def _cookie_kwargs():
    cfg = settings.SIMPLE_JWT
    return dict(
        httponly=True,
        secure=cfg["AUTH_COOKIE_SECURE"],
        samesite=cfg["AUTH_COOKIE_SAMESITE"],
        path=cfg["AUTH_COOKIE_PATH"],
        domain=cfg["AUTH_COOKIE_DOMAIN"],
    )


def set_auth_cookies(response, access_token, refresh_token=None):
    """Attach the access (and optionally refresh) token as HttpOnly cookies."""
    cfg = settings.SIMPLE_JWT
    kwargs = _cookie_kwargs()
    response.set_cookie(
        cfg["AUTH_COOKIE"],
        access_token,
        max_age=int(cfg["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        **kwargs,
    )
    if refresh_token is not None:
        response.set_cookie(
            cfg["AUTH_COOKIE_REFRESH"],
            refresh_token,
            max_age=int(cfg["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            **kwargs,
        )
    return response


def clear_auth_cookies(response):
    cfg = settings.SIMPLE_JWT
    response.delete_cookie(
        cfg["AUTH_COOKIE"],
        path=cfg["AUTH_COOKIE_PATH"],
        domain=cfg["AUTH_COOKIE_DOMAIN"],
    )
    response.delete_cookie(
        cfg["AUTH_COOKIE_REFRESH"],
        path=cfg["AUTH_COOKIE_PATH"],
        domain=cfg["AUTH_COOKIE_DOMAIN"],
    )
    return response
