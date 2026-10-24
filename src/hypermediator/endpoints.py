"""Resolve a URL name to its declared affordance, and evaluate see-it and use-it for a request."""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from django.core.exceptions import ImproperlyConfigured
from django.core.signals import setting_changed
from django.db.models import Model
from django.http import HttpRequest
from django.urls import NoReverseMatch, URLPattern, URLResolver, get_resolver, reverse

from hypermediator.affordances import Affordance, Placement
from hypermediator.views import FunctionDeclaration

State = Literal["enabled", "disabled", "hidden"]


def dom_id_for(name: str, obj: Model | None = None) -> str:
    """The wrapper id: ``hm-{name}``, or ``hm-{name}-{pk}`` when bound to an object. A
    namespace's ``:`` becomes ``-``, so the id is usable as a CSS selector."""
    base = f"hm-{name.replace(':', '-')}"
    return base if obj is None else f"{base}-{obj.pk}"


@dataclass(frozen=True)
class Endpoint:
    """``methods`` is the declared set ("GET", plus "POST" when the view handles POST), not
    derived from Django's handlers; mismatches with Django's Allow are reported by system
    checks."""

    name: str
    affordance: Affordance
    methods: frozenset[str]
    has_fields: bool
    view_class: type | None = field(default=None, compare=False, repr=False)
    view_initkwargs: Mapping[str, Any] = field(default_factory=dict, compare=False, repr=False)
    declaration: FunctionDeclaration | None = field(default=None, compare=False, repr=False)
    route_kwargs: frozenset[str] = field(default=frozenset(), compare=False, repr=False)

    def url_kwargs(self, obj: Model | None) -> dict[str, Any]:
        """The URL kwargs that identify ``obj`` on this endpoint's route."""
        if obj is None:
            return {}
        if self.declaration is not None:
            custom = self.declaration.url_kwargs
            return {"pk": obj.pk} if custom is None else dict(custom(obj))
        pk_kwarg: str = getattr(self.view_class, "pk_url_kwarg", "pk")
        if pk_kwarg in self.route_kwargs:
            return {pk_kwarg: obj.pk}
        slug_kwarg: str = getattr(self.view_class, "slug_url_kwarg", "slug")
        if slug_kwarg not in self.route_kwargs:
            raise ImproperlyConfigured(
                f"URL '{self.name}' captures {sorted(self.route_kwargs)}, which includes neither "
                f"pk_url_kwarg ('{pk_kwarg}') nor slug_url_kwarg ('{slug_kwarg}'); "
                "hypermediator cannot build its URL for an object."
            )
        slug_field: str = getattr(self.view_class, "slug_field", "slug")
        return {slug_kwarg: getattr(obj, slug_field)}

    def _instantiate(self, request: HttpRequest, kwargs: Mapping[str, Any]) -> Any:
        assert self.view_class is not None  # nosec B101
        view = self.view_class(**self.view_initkwargs)
        view.setup(request, **kwargs)
        return view

    def see(self, request: HttpRequest, kwargs: Mapping[str, Any]) -> bool:
        """The see-it check: may this user know the control exists?"""
        if self.declaration is not None:
            permissions = self.declaration.permission
            return not permissions or request.user.has_perms(permissions)
        has_permission = getattr(self._instantiate(request, kwargs), "has_permission", None)
        return True if has_permission is None else bool(has_permission())

    def use(self, request: HttpRequest, kwargs: Mapping[str, Any], obj: Model | None) -> str | None:
        """The use-it check: a reason the control cannot be used now, or None."""
        if self.declaration is not None:
            check = self.declaration.unavailable
            return None if check is None else check(request, obj)
        reason: str | None = self._instantiate(request, kwargs).unavailable(obj)
        return reason


@dataclass(frozen=True)
class Bound:
    endpoint: Endpoint
    url: str
    obj: Model | None
    state: State
    reason: str | None
    dom_id: str
    placement: Placement


def _allowed_methods(view_class: type) -> frozenset[str]:
    return frozenset({"GET", "POST"} if hasattr(view_class, "post") else {"GET"})


def url_routes() -> Iterator[tuple[str | None, URLPattern, frozenset[str]]]:
    """Every route in the URLconf: its namespaced name (None when unnamed), the pattern, and the
    kwargs captured by the route and every enclosing include() prefix."""

    def walk(
        patterns: Iterable[URLPattern | URLResolver], prefix: str, kwargs: frozenset[str]
    ) -> Iterator[tuple[str | None, URLPattern, frozenset[str]]]:
        for pattern in patterns:
            captured = kwargs | frozenset(pattern.pattern.regex.groupindex)
            if isinstance(pattern, URLResolver):
                inner = f"{prefix}{pattern.namespace}:" if pattern.namespace else prefix
                yield from walk(pattern.url_patterns, inner, captured)
            else:
                yield (f"{prefix}{pattern.name}" if pattern.name else None), pattern, captured

    return walk(get_resolver().url_patterns, "", frozenset())


def _find_route(url_name: str) -> tuple[URLPattern, frozenset[str]]:
    """The route with this (namespaced) name and its captured kwargs; no URL kwargs are needed."""
    for name, pattern, kwargs in url_routes():
        if name == url_name:
            return pattern, kwargs
    raise NoReverseMatch(f"Reverse for '{url_name}' not found.")


@functools.cache
def endpoint_for(url_name: str) -> Endpoint | None:
    """The endpoint behind a URL name, or None when its view declares no affordance."""
    route, route_kwargs = _find_route(url_name)
    func: Callable[..., Any] = route.callback
    declaration: FunctionDeclaration | None = getattr(func, "hypermediator", None)
    if declaration is not None:
        return Endpoint(
            name=url_name,
            affordance=declaration.affordance,
            methods=frozenset({"GET", "POST"}),
            has_fields=declaration.form_class is not None,
            declaration=declaration,
            route_kwargs=route_kwargs,
        )
    view_class: type | None = getattr(func, "view_class", None)
    affordance = getattr(view_class, "affordance", None)
    if view_class is None or affordance is None:
        return None
    return Endpoint(
        name=url_name,
        affordance=affordance,
        methods=_allowed_methods(view_class),
        has_fields=(
            getattr(view_class, "form_class", None) is not None
            or getattr(view_class, "fields", None) is not None
        ),
        view_class=view_class,
        view_initkwargs=getattr(func, "view_initkwargs", {}),
        route_kwargs=route_kwargs,
    )


def _reset_cache(*, setting: str, **kwargs: object) -> None:
    if setting == "ROOT_URLCONF":
        endpoint_for.cache_clear()


setting_changed.connect(_reset_cache)


def bound_for(
    endpoint: Endpoint,
    obj: Model | None,
    state: State,
    reason: str | None,
    placement: Placement | None = None,
) -> Bound:
    """``endpoint`` bound to ``obj``: its URL, wrapper id and placement (declared, else ITEM
    for an object and PAGE otherwise)."""
    return Bound(
        endpoint=endpoint,
        url=reverse(endpoint.name, kwargs=endpoint.url_kwargs(obj)),
        obj=obj,
        state=state,
        reason=reason,
        dom_id=dom_id_for(endpoint.name, obj),
        placement=(
            placement
            or endpoint.affordance.placement
            or (Placement.PAGE if obj is None else Placement.ITEM)
        ),
    )


def bind(
    request: HttpRequest,
    url_name: str,
    obj: Model | None = None,
    *,
    placement_override: Placement | None = None,
) -> Bound:
    """Evaluate see-it and use-it for ``url_name`` (bound to ``obj``) against ``request``."""
    endpoint = endpoint_for(url_name)
    if endpoint is None:
        raise LookupError(f"The view named {url_name!r} declares no affordance")
    kwargs = endpoint.url_kwargs(obj)
    state: State
    reason: str | None = None
    if not endpoint.see(request, kwargs):
        state = "hidden"
    else:
        reason = endpoint.use(request, kwargs, obj)
        state = "enabled" if reason is None else "disabled"
    return bound_for(endpoint, obj, state, reason, placement_override)


__all__ = ["Bound", "Endpoint", "bind", "bound_for", "dom_id_for", "endpoint_for"]
