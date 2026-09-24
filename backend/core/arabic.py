"""Arabic-insensitive search.

Shop staff type product names the way they speak them: "ارز" for "أرز",
"بسمتى" for "بسمتي", "علبه" for "علبة", with or without a tatweel or a
shadda. An exact `icontains` missed all of those, so the till's search
looked empty for an item on the shelf.

Folding maps every such variant to one form — hamza-carrying alefs to a
bare alef, taa marbuta to haa, alef maqsura to yaa, Arabic-Indic digits to
ASCII — and drops tatweel and the short-vowel marks. The same fold is
applied to the search terms (in Python) and to the searched columns (in
SQL), so no stored column, backfill or trigger is needed and a row written
by any path — import, bulk create, admin — is found the same way.

In SQL the fold is one call: PostgreSQL's TRANSLATE, and on SQLite a Python
function registered on each connection. Nesting ~45 REPLACE calls overflowed
the parser of older SQLite builds ("parser stack overflow").
"""
from django.db.backends.signals import connection_created
from django.db.models import CharField, F, Func, Value
from django.db.models.functions import Replace
from django.dispatch import receiver
from rest_framework.filters import SearchFilter

# (variant, folded). Order does not matter: no folded form is a variant.
_FOLDS = [
    ("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"),
    ("ة", "ه"), ("ى", "ي"), ("ؤ", "و"), ("ئ", "ي"),
    ("ـ", ""),  # tatweel
    *[(chr(code), "") for code in range(0x064B, 0x0653)],  # tanween, harakat, shadda, sukun
    ("ٰ", ""),  # superscript alef
    *[(chr(0x0660 + digit), str(digit)) for digit in range(10)],  # ٠-٩
    *[(chr(0x06F0 + digit), str(digit)) for digit in range(10)],  # ۰-۹ (Persian)
]
_TABLE = {ord(variant): folded for variant, folded in _FOLDS}


def fold_arabic(text):
    """The search form of `text` (see module docstring)."""
    return str(text or "").translate(_TABLE)


# TRANSLATE maps the i-th character of `from` to the i-th of `to` and drops
# the characters of `from` that have no counterpart, so the one-to-one folds
# come first and the dropped characters last.
_MAPPED = [(v, f) for v, f in _FOLDS if f]
_DROPPED = [v for v, f in _FOLDS if not f]
_TRANSLATE_FROM = "".join(v for v, _ in _MAPPED) + "".join(_DROPPED)
_TRANSLATE_TO = "".join(f for _, f in _MAPPED)


def _register_sqlite_fold(connection):
    connection.connection.create_function("ar_fold", 1, fold_arabic, deterministic=True)


@receiver(connection_created)
def _on_connection(sender, connection, **kwargs):
    if connection.vendor == "sqlite":
        _register_sqlite_fold(connection)


class ArabicFold(Func):
    """fold_arabic() in SQL."""

    output_field = CharField()
    arity = 1

    def as_sql(self, compiler, connection, **extra_context):
        # Any other backend: the portable (if deep) REPLACE chain.
        expression = self.source_expressions[0]
        for variant, folded in _FOLDS:
            expression = Replace(expression, Value(variant), Value(folded))
        return compiler.compile(expression)

    def as_sqlite(self, compiler, connection, **extra_context):
        # A connection opened before this module was imported missed the
        # signal; registering again is harmless.
        connection.ensure_connection()
        _register_sqlite_fold(connection)
        sql, params = compiler.compile(self.source_expressions[0])
        return f"ar_fold({sql})", params

    def as_postgresql(self, compiler, connection, **extra_context):
        sql, params = compiler.compile(self.source_expressions[0])
        return f"TRANSLATE({sql}, %s, %s)", (*params, _TRANSLATE_FROM, _TRANSLATE_TO)


def folded_field(name):
    """A database expression equal to fold_arabic(<column>)."""
    return ArabicFold(F(name))


def _alias(field):
    return f"{field.replace('__', '_')}_folded"


class ArabicSearchFilter(SearchFilter):
    """SearchFilter whose terms are folded, and which also matches the view's
    `arabic_search_fields` in folded form.

    Folding a term never breaks a match on a Latin field (a SKU, a barcode):
    it only changes Arabic letters and turns Arabic-Indic digits into the
    ASCII digits those fields hold."""

    def _arabic_fields(self, view):
        return tuple(getattr(view, "arabic_search_fields", ()) or ())

    def get_search_fields(self, view, request):
        base = [
            field for field in (super().get_search_fields(view, request) or [])
            if field not in self._arabic_fields(view)
        ]
        return base + [_alias(field) for field in self._arabic_fields(view)]

    def get_search_terms(self, request):
        return [fold_arabic(term) for term in super().get_search_terms(request)]

    def filter_queryset(self, request, queryset, view):
        fields = self._arabic_fields(view)
        if fields and self.get_search_terms(request):
            queryset = queryset.annotate(
                **{_alias(field): folded_field(field) for field in fields}
            )
        return super().filter_queryset(request, queryset, view)
