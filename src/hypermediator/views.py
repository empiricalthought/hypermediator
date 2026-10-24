"""Declare an affordance on a view; enforce see-it and use-it when the control is submitted."""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, TypeVar, cast

from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db.models import Model
from django.forms import BaseForm
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import get_object_or_404, render
from django.views.generic.detail import SingleObjectMixin

from hypermediator.affordances import Affordance, Placement
from hypermediator.microdata import ITEMTYPE

if TYPE_CHECKING:
    from hypermediator.endpoints import Endpoint

_V = TypeVar("_V", bound=Callable[..., HttpResponseBase])


@dataclass(frozen=True)
class FunctionDeclaration:
    """What ``@affordance`` records on a function view."""

    affordance: Affordance
    permission: tuple[str, ...] = ()
    model: type[Model] | None = None
    unavailable: Callable[[HttpRequest, Any], str | None] | None = None
    partial: str | None = None
    placements: Mapping[str, Placement] = MappingProxyType({})
    form_class: type[BaseForm] | None = None


def unavailable_response(
    request: HttpRequest, endpoint: Endpoint, obj: Model | None, reason: str
) -> HttpResponse:
    """The 409 for a use-it failure on submit: the disabled control, with the page's wrapper id."""
    from hypermediator.endpoints import dom_id_for

    dom_id = dom_id_for(endpoint.name, obj)
    get_absolute_url = getattr(obj, "get_absolute_url", None)
    response = render(
        request,
        "hypermediator/unavailable.html",
        {
            "dom_id": dom_id,
            "name": endpoint.name,
            "label": endpoint.affordance.label,
            "rels": endpoint.affordance.rel,
            "reason": reason,
            "back_url": get_absolute_url() if callable(get_absolute_url) else None,
            "itemtype": ITEMTYPE,
        },
        status=409,
    )
    if request.headers.get("HX-Request") == "true":
        response.headers["HX-Retarget"] = f"#{dom_id}"
        response.headers["HX-Reswap"] = "outerHTML"
        response.headers["HX-Reselect"] = f"#{dom_id}"
    return response


def _current_endpoint(request: HttpRequest) -> Endpoint:
    from hypermediator.endpoints import endpoint_for

    match = request.resolver_match
    endpoint = endpoint_for(match.url_name) if match and match.url_name else None
    if endpoint is None:
        raise ImproperlyConfigured("A hypermediator view must be routed under a URL name")
    return endpoint


class HypermediaMixin:
    """Declare an affordance on a class-based view and refuse unavailable POSTs with a 409."""

    affordance: Affordance | None = None
    placements: Mapping[str, Placement] = MappingProxyType({})
    partial: str | None = None

    def unavailable(self, obj: object | None) -> str | None:
        return None

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        obj = self.get_object() if isinstance(self, SingleObjectMixin) else None
        reason = self.unavailable(obj)
        if reason is not None:
            return unavailable_response(request, _current_endpoint(request), obj, reason)
        parent = getattr(super(), "post", None)
        if parent is None:
            return self.http_method_not_allowed(request, *args, **kwargs)  # type: ignore[attr-defined,no-any-return]
        return cast(HttpResponseBase, parent(request, *args, **kwargs))

    def _allowed_methods(self) -> list[str]:
        # This mixin always defines post(); only advertise POST when the view really handles it.
        methods: list[str] = super()._allowed_methods()  # type: ignore[misc]
        if getattr(super(), "post", None) is None:
            methods.remove("POST")
        return methods


def affordance(
    *,
    label: str,
    rel: Sequence[str] = (),
    placement: Placement | None = None,
    trigger: str | None = None,
    permission: str | Sequence[str] | None = None,
    model: type[Model] | None = None,
    unavailable: Callable[[HttpRequest, Any], str | None] | None = None,
    partial: str | None = None,
    placements: Mapping[str, Placement] | None = None,
    form_class: type[BaseForm] | None = None,
) -> Callable[[_V], _V]:
    """Declare an affordance on a function view, enforcing ``permission`` (403) and, on POST,
    ``unavailable`` (409)."""
    permissions = (permission,) if isinstance(permission, str) else tuple(permission or ())
    declaration = FunctionDeclaration(
        affordance=Affordance(label=label, rel=tuple(rel), placement=placement, trigger=trigger),
        permission=permissions,
        model=model,
        unavailable=unavailable,
        partial=partial,
        placements=MappingProxyType(dict(placements or {})),
        form_class=form_class,
    )

    def decorator(view: _V) -> _V:
        @functools.wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
            if permissions and not request.user.has_perms(permissions):
                raise PermissionDenied
            if request.method == "POST" and unavailable is not None:
                obj: Model | None = None
                if model is not None:
                    if "pk" not in kwargs:
                        raise ImproperlyConfigured("@affordance(model=...) needs a pk URL kwarg")
                    obj = get_object_or_404(model, pk=kwargs["pk"])
                reason = unavailable(request, obj)
                if reason is not None:
                    return unavailable_response(request, _current_endpoint(request), obj, reason)
            return view(request, *args, **kwargs)

        wrapper.hypermediator = declaration  # type: ignore[attr-defined]
        return cast(_V, wrapper)

    return decorator
