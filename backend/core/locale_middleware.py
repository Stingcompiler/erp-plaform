"""LocaleMiddleware for an app whose language lives in a cookie.

Django's LocaleMiddleware consults the ``Accept-Language`` header when the
language cookie is absent, so a browser installed in English turned every
refusal English on an Arabic screen until the person had toggled the
language once. The app's screen language is the only thing that should
decide the API's language: cookie first, then the site default — never the
browser header, which describes the OS, not the screen.
"""

from django.conf import settings
from django.middleware.locale import LocaleMiddleware
from django.utils import translation


class CookieOnlyLocaleMiddleware(LocaleMiddleware):
    def process_request(self, request):
        cookie = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        supported = {code for code, _name in settings.LANGUAGES}
        language = cookie if cookie in supported else settings.LANGUAGE_CODE
        translation.activate(language)
        request.LANGUAGE_CODE = translation.get_language()
