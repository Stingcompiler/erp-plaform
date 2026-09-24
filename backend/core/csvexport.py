"""Spreadsheet-safe CSV downloads.

Every CSV the application hands out goes through here, for two reasons:

* A UTF-8 byte-order mark first, so Excel opens Arabic names as UTF-8
  instead of Latin-1 mojibake.
* Formula injection: a customer named ``=HYPERLINK(...)`` (or a lead's note
  starting with ``+``, ``-``, ``@``) is executed by Excel/LibreOffice when the
  export is opened. Such text cells are prefixed with an apostrophe so the
  spreadsheet shows them as text. Numbers are left alone — a Decimal is never
  touched, and a string that is just a number ("-12.50") cannot be a formula,
  so a negative balance still sums in the sheet.
"""
import csv
import re

from django.http import HttpResponse

BOM = "﻿"
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_PLAIN_NUMBER = re.compile(r"[+-]?\d+(\.\d+)?")


def safe_cell(value):
    """The value as a spreadsheet will treat it: text cells that a
    spreadsheet would evaluate get a leading apostrophe."""
    if (
        isinstance(value, str)
        and value.startswith(_FORMULA_START)
        and not _PLAIN_NUMBER.fullmatch(value)
    ):
        return "'" + value
    return value


class SafeWriter:
    """`csv.writer` that neutralises every cell it writes."""

    def __init__(self, stream):
        self._writer = csv.writer(stream)

    def writerow(self, row):
        return self._writer.writerow([safe_cell(value) for value in row])

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


def csv_download(filename):
    """An attachment response with the BOM written, and a safe writer on it."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write(BOM)
    return response, SafeWriter(response)


def rows_download(filename, header, rows):
    response, writer = csv_download(filename)
    writer.writerow(header)
    writer.writerows(rows)
    return response
