"""Arabic-insensitive search.

Shop staff type product names the way they speak them: "ارز" for "أرز",
"بسمتى" for "بسمتي", "علبه" for "علبة", with or without a tatweel or a
shadda. An exact `icontains` missed all of those, so the till's search
looked empty for an item on the shelf.

Folding maps every such variant to one form — hamza-carrying alefs to a
bare alef, taa marbuta to haa, alef maqsura to yaa, Arabic-Indic digits to
ASCII — and drops tatweel and the short-vowel marks. The same fold is
applied to the search terms (in Python) and to the searched columns (as
nested SQL REPLACE, which SQLite and PostgreSQL both have), so no stored
column, backfill or trigger is needed and a row written by any path —
import, bulk create, admin — is found the same way.
"""
from django.db.models import F, Value
from django.db.models.functions import Replace
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


def folded_field(name):
    """A database expression equal to fold_arabic(<column>)."""
    expression = F(name)
    for variant, folded in _FOLDS:
        expression = Replace(expression, Value(variant), Value(folded))
    return expression


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
