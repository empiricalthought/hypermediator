"""The response pipeline shared by class-based and function views: partial selection, 422 on
invalid forms, ``Vary``, and htmx redirects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.forms import BaseForm
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import render as django_render
from django.utils.cache import patch_vary_headers

from hypermediator.affordances import Placement
from hypermediator.htmx import is_htmx, is_partial, is_unsafe, redirect_to_location

VARY = ("HX-Request", "HX-Request-Type")


def partial_name(request: HttpRequest, template_name: str, partial: str | None) -> str:
    """``template#partial`` for a partial request on a view that declares one."""
    if partial is not None and is_partial(request):
        return f"{template_name}#{partial}"
    return template_name


def has_invalid_form(context: Mapping[str, Any] | None) -> bool:
    return any(
        isinstance(value, BaseForm) and value.is_bound and bool(value.errors)
        for value in (context or {}).values()
    )


def resolve_placement(declared: Placement | None, url_kwargs: Mapping[str, Any]) -> Placement:
    """The declared placement; otherwise ITEM when the URL identifies an object, else PAGE."""
    if declared is not None:
        return declared
    identified = "pk" in url_kwargs or "slug" in url_kwargs
    return Placement.ITEM if identified else Placement.PAGE


def finish_response(
    request: HttpRequest, response: HttpResponseBase, placement: Placement
) -> HttpResponseBase:
    """Convert a PAGE-placement redirect to ``HX-Location`` for htmx, and add ``Vary``."""
    if is_htmx(request) and is_unsafe(request) and placement is Placement.PAGE:
        response = redirect_to_location(response)
    patch_vary_headers(response, VARY)
    return response


def render(
    request: HttpRequest,
    template_name: str,
    context: Mapping[str, Any] | None = None,
    *,
    partial: str | None = None,
    status: int | None = None,
) -> HttpResponse:
    """Drop-in for ``django.shortcuts.render`` with partials, 422 on invalid forms, and Vary."""
    if status is None and has_invalid_form(context):
        status = 422
    response = django_render(
        request, partial_name(request, template_name, partial), context, status=status
    )
    patch_vary_headers(response, VARY)
    return response
