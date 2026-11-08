"""
src/mitespotter_api/errors.py
Errors that name the form field they are about, so a form can mark that field

Responses look like {"status_code": 400, "detail": "<message>", "extra": {"field": "name"}}.

Created: 2026-11-08
Authors: Maxence Morel Dierckx
"""
from __future__ import annotations


from litestar.exceptions import ClientException


def field_error(message: str, field: str) -> ClientException:
    return ClientException(message, extra={"field": field})
