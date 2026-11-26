"""Private scalar normalization shared by both transaction record parsers.

PropertyRadar's published spec declares these record fields as strings, but
live rows send JSON numbers and may send other scalars. Each accepted scalar
becomes exact text, so record values stay strings. Nothing here raises; each
parser maps a rejection to its own ``record_field_type`` error.
"""

from __future__ import annotations

import math
from decimal import Decimal

RECORD_FLAG_FIELDS = ("hasDocumentImage", "isFirstCurrentOwnerRecord", "isParentType")
RECORD_ENUM_FIELDS = ("Status", "DocGroup")
RECORD_VALUE_TYPES = ("string", "integer", "number", "boolean", "null")
RECORD_STRING_POLICY = "exact_str_preserved"
RECORD_NULL_POLICY = "omitted_preserved_as_unavailable"
RECORD_BOOLEAN_POLICY = "flag_fields_only_true_1_false_0"
RECORD_INTEGER_POLICY = "exact_int_absolute_value_maximum_64_digits_signed_decimal_text"
RECORD_NUMBER_POLICY = (
    "finite_float_decimal_repr_plain_form_absolute_value_maximum_64_characters_signed"
)
RECORD_ENUM_POLICY = "exact_str_or_null_only"
RECORD_VALUE_BASIS = (
    "spec_declares_strings_live_integers_observed_floats_booleans_nulls_tolerated"
)
_MAXIMUM_LENGTH = 64
_INTEGER_LIMIT = 10**_MAXIMUM_LENGTH


def record_value_omitted(field: str, value: object) -> bool:
    """Return whether a null value marks an unavailable optional field."""
    return value is None and field != "RecDate"


def record_scalar_text(field: str, value: object) -> str | None:
    """Return exact text for one record scalar, or None to reject it."""
    if type(value) is str:
        return value
    if type(value) is bool:
        if field in RECORD_FLAG_FIELDS:
            return "1" if value else "0"
        return None
    if field == "RecDate" or field in RECORD_ENUM_FIELDS:
        return None
    if type(value) is int:
        if -_INTEGER_LIMIT < value < _INTEGER_LIMIT:
            return str(value)
        return None
    if type(value) is float and math.isfinite(value):
        if value == 0 and math.copysign(1.0, value) < 0:
            return None
        text = format(Decimal(repr(abs(value))), "f")
        if len(text) <= _MAXIMUM_LENGTH:
            return f"-{text}" if value < 0 else text
    return None
