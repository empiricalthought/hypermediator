"""Response-side hypermedia: the ``Link`` header and the missing-item reswap."""

from __future__ import annotations

from collections.abc import Callable

from django.http import HttpRequest
from django.http.response import HttpResponseBase
from django.utils.html import escape

from hypermediator.endpoints import Bound
from hypermediator.htmx import is_htmx


def _link_entries(rendered: list[Bound]) -> list[str]:
    entries: list[str] = []
    for bound in rendered:
        rel = " ".join(bound.endpoint.affordance.rel)
        if bound.state != "enabled" or not bound.link_header or not rel:
            continue
        entry = f'<{bound.url}>; rel="{rel}"'
        if entry not in entries:
            entries.append(entry)
    return entries


def _item_missing(request: HttpRequest, response: HttpResponseBase) -> bool:
    key = request.headers.get("HX-Hm-Item")
    if not (is_htmx(request) and key) or response.status_code != 200 or response.streaming:
        return False
    body = response.content.decode(response.charset, errors="replace")  # type: ignore[attr-defined]
    return f'data-hm-item="{escape(key)}"' not in body


class HypermediatorMiddleware:
    """Adds ``Link`` for the enabled, rel'd affordances a response rendered that are selected
    for it (``link_header``, as the page may override), and tells htmx to
    swap nothing when the item it asked to refresh is absent from the response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        response = self.get_response(request)
        entries = _link_entries(getattr(request, "_hm_rendered", []))
        if entries:
            existing = response.headers.get("Link")
            response.headers["Link"] = ", ".join([existing, *entries] if existing else entries)
        if _item_missing(request, response):
            response.headers["HX-Reswap"] = "none"
        return response
