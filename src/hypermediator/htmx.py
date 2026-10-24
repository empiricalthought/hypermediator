"""Reading htmx's request headers and speaking its response headers."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase

_UNSAFE_EXCLUDED = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def is_partial(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request-Type") == "partial"


def is_unsafe(request: HttpRequest) -> bool:
    return (request.method or "GET").upper() not in _UNSAFE_EXCLUDED


def redirect_to_location(response: HttpResponseBase) -> HttpResponseBase:
    """A 3xx with a Location becomes a 200 carrying ``HX-Location``, so htmx navigates
    client-side instead of fetching the redirect target into a swap."""
    location = response.headers.get("Location")
    if not 300 <= response.status_code < 400 or not location:
        return response
    converted = HttpResponse(status=200)
    converted.headers["HX-Location"] = location
    for key, morsel in response.cookies.items():
        converted.cookies[key] = morsel
    return converted
