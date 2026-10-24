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
from hypermediator.htmx import is_htmx, is_partial
from hypermediator.shortcuts import finish_response, handler_redirect, partial_name

if TYPE_CHECKING:
    from hypermediator.endpoints import Endpoint

_SAFE_METHODS = frozenset({"get", "head", "options"})
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
    link_headers: Mapping[str, bool] = MappingProxyType({})
    form_class: type[BaseForm] | None = None
    url_kwargs: Callable[[Any], Mapping[str, Any]] | None = None


def unavailable_response(
    request: HttpRequest, endpoint: Endpoint, obj: Model | None, reason: str
) -> HttpResponse:
    """The 409 for a use-it failure on submit: the disabled control, with the page's wrapper id."""
    from hypermediator.endpoints import bound_for
    from hypermediator.templatetags.hypermediator import render_link

    bound = bound_for(endpoint, obj, "disabled", reason)
    dom_id = bound.dom_id
    get_absolute_url = getattr(obj, "get_absolute_url", None)
    response = render(
        request,
        "hypermediator/unavailable.html",
        {
            "label": endpoint.affordance.label,
            "control": render_link(request, bound),
            "back_url": get_absolute_url() if callable(get_absolute_url) else None,
        },
        status=409,
    )
    if is_htmx(request):
        response.headers["HX-Retarget"] = f"#{dom_id}"
        response.headers["HX-Reswap"] = "outerHTML"
        response.headers["HX-Reselect"] = f"#{dom_id}"
    return response


def _current_endpoint(request: HttpRequest) -> Endpoint:
    from hypermediator.endpoints import endpoint_for

    match = request.resolver_match
    endpoint = endpoint_for(match.view_name) if match and match.view_name else None
    if endpoint is None:
        raise ImproperlyConfigured("A hypermediator view must be routed under a URL name")
    return endpoint


class HypermediaMixin:
    """Declare an affordance on a class-based view and refuse unavailable submits with a 409."""

    affordance: Affordance | None = None
    placements: Mapping[str, Placement] = MappingProxyType({})
    link_headers: Mapping[str, bool] = MappingProxyType({})
    partial: str | None = None

    def unavailable(self, obj: object | None) -> str | None:
        return None

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        # Guard every state-changing handler. Wrapping the handler on the instance leaves
        # Django's dispatch, Allow and 405 behaviour untouched, and means any auth mixin's
        # dispatch (see-it) has run before the guard (use-it), whatever the MRO.
        method = (request.method or "").lower()
        if method not in _SAFE_METHODS and method in getattr(self, "http_method_names", ()):
            handler = getattr(self, method, None)
            if handler is not None:
                setattr(self, method, self._guarded(handler))
        response: HttpResponseBase = super().dispatch(request, *args, **kwargs)  # type: ignore[misc]
        return finish_response(request, response)

    def get_template_names(self) -> list[str]:
        """The declared partial of each template, for a partial request."""
        names: list[str] = super().get_template_names()  # type: ignore[misc]
        request: HttpRequest = self.request  # type: ignore[attr-defined]
        if self.partial is None or not is_partial(request):
            return names
        return [partial_name(request, name, self.partial) for name in names]

    def form_invalid(self, form: BaseForm) -> HttpResponse:
        """An invalid submit is a 422, so htmx swaps the re-rendered form."""
        context = self.get_context_data(form=form)  # type: ignore[attr-defined]
        response: HttpResponse = self.render_to_response(context, status=422)  # type: ignore[attr-defined]
        return response

    def _guarded(self, handler: Callable[..., HttpResponseBase]) -> Callable[..., HttpResponseBase]:
        @functools.wraps(handler)
        def guarded(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
            obj = self._use_object()
            reason = self.unavailable(obj)
            if reason is not None:
                return unavailable_response(request, _current_endpoint(request), obj, reason)
            # Only the handler's own redirect is converted; an auth mixin's is Django's.
            return handler_redirect(request, handler(request, *args, **kwargs))

        return guarded

    def _use_object(self) -> Any:
        """The object use-it is judged on: loaded only when the URL identifies one."""
        if not isinstance(self, SingleObjectMixin):
            return None
        url_kwargs: Mapping[str, Any] = getattr(self, "kwargs", {})
        if self.pk_url_kwarg in url_kwargs or self.slug_url_kwarg in url_kwargs:
            return self.get_object()
        return None


def affordance(
    *,
    label: str,
    rel: Sequence[str] = (),
    placement: Placement | None = None,
    trigger: str | None = None,
    link_header: bool = False,
    permission: str | Sequence[str] | None = None,
    model: type[Model] | None = None,
    unavailable: Callable[[HttpRequest, Any], str | None] | None = None,
    partial: str | None = None,
    placements: Mapping[str, Placement] | None = None,
    link_headers: Mapping[str, bool] | None = None,
    form_class: type[BaseForm] | None = None,
    url_kwargs: Callable[[Any], Mapping[str, Any]] | None = None,
) -> Callable[[_V], _V]:
    """Declare an affordance on a function view, enforcing ``permission`` (a login redirect
    for an anonymous user, else 403, as ``permission_required``) and, on every unsafe method,
    ``unavailable`` (409). ``link_header`` selects it for the ``Link`` header; ``link_headers``
    overrides that for other affordances this view's page references, by URL name, as
    ``placements`` does. ``url_kwargs`` maps a bound object to the route's URL kwargs
    (default ``{"pk": obj.pk}``)."""
    if isinstance(rel, str):
        raise TypeError(f"Affordance rel must be a sequence of tokens, not {rel!r}")
    permissions = (permission,) if isinstance(permission, str) else tuple(permission or ())
    declaration = FunctionDeclaration(
        affordance=Affordance(
            label=label,
            rel=tuple(rel),
            placement=placement,
            trigger=trigger,
            link_header=link_header,
        ),
        permission=permissions,
        model=model,
        unavailable=unavailable,
        partial=partial,
        placements=MappingProxyType(dict(placements or {})),
        link_headers=MappingProxyType(dict(link_headers or {})),
        form_class=form_class,
        url_kwargs=url_kwargs,
    )

    def decorator(view: _V) -> _V:
        @functools.wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
            if permissions and not request.user.has_perms(permissions):
                if not request.user.is_authenticated:
                    # Imported here: auth's views load its models, which need the app registry.
                    from django.contrib.auth.views import redirect_to_login

                    return finish_response(request, redirect_to_login(request.get_full_path()))
                raise PermissionDenied
            method = (request.method or "").lower()
            if method not in _SAFE_METHODS and unavailable is not None:
                obj: Model | None = None
                if model is not None:
                    if "pk" not in kwargs:
                        raise ImproperlyConfigured("@affordance(model=...) needs a pk URL kwarg")
                    obj = get_object_or_404(model, pk=kwargs["pk"])
                reason = unavailable(request, obj)
                if reason is not None:
                    response = unavailable_response(
                        request, _current_endpoint(request), obj, reason
                    )
                    return finish_response(request, response)
            return finish_response(
                request, handler_redirect(request, view(request, *args, **kwargs))
            )

        wrapper.hypermediator = declaration  # type: ignore[attr-defined]
        return cast(_V, wrapper)

    return decorator
