"""Resolve a URL name to its declared affordance, and evaluate see-it and use-it for a request."""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from django.core.signals import setting_changed
from django.db.models import Model
from django.http import HttpRequest
from django.urls import NoReverseMatch, URLPattern, URLResolver, get_resolver, reverse

from hypermediator.affordances import Affordance, Placement
from hypermediator.views import FunctionDeclaration

State = Literal["enabled", "disabled", "hidden"]


def dom_id_for(name: str, obj: Model | None = None) -> str:
    """The wrapper id: ``hm-{name}``, or ``hm-{name}-{pk}`` when bound to an object."""
    return f"hm-{name}" if obj is None else f"hm-{name}-{obj.pk}"


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

    def _instantiate(self, request: HttpRequest, kwargs: Mapping[str, Any]) -> Any:
        assert self.view_class is not None
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


def _find_callback(url_name: str) -> Callable[..., Any]:
    """Walk the URLconf for the pattern with this (namespaced) name; no URL kwargs are needed."""

    def walk(
        patterns: Iterable[URLPattern | URLResolver], prefix: str
    ) -> Callable[..., Any] | None:
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                inner = f"{prefix}{pattern.namespace}:" if pattern.namespace else prefix
                found = walk(pattern.url_patterns, inner)
                if found is not None:
                    return found
            elif pattern.name and f"{prefix}{pattern.name}" == url_name:
                return pattern.callback
        return None

    callback = walk(get_resolver().url_patterns, "")
    if callback is None:
        raise NoReverseMatch(f"Reverse for '{url_name}' not found.")
    return callback


@functools.cache
def endpoint_for(url_name: str) -> Endpoint | None:
    """The endpoint behind a URL name, or None when its view declares no affordance."""
    func = _find_callback(url_name)
    declaration: FunctionDeclaration | None = getattr(func, "hypermediator", None)
    if declaration is not None:
        return Endpoint(
            name=url_name,
            affordance=declaration.affordance,
            methods=frozenset({"GET", "POST"}),
            has_fields=declaration.form_class is not None,
            declaration=declaration,
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
    )


def _reset_cache(*, setting: str, **kwargs: object) -> None:
    if setting == "ROOT_URLCONF":
        endpoint_for.cache_clear()


setting_changed.connect(_reset_cache)


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
    kwargs: dict[str, Any] = {} if obj is None else {"pk": obj.pk}
    placement = (
        placement_override
        or endpoint.affordance.placement
        or (Placement.PAGE if obj is None else Placement.ITEM)
    )
    state: State
    reason: str | None = None
    if not endpoint.see(request, kwargs):
        state = "hidden"
    else:
        reason = endpoint.use(request, kwargs, obj)
        state = "enabled" if reason is None else "disabled"
    return Bound(
        endpoint=endpoint,
        url=reverse(url_name, kwargs=kwargs),
        obj=obj,
        state=state,
        reason=reason,
        dom_id=dom_id_for(url_name, obj),
        placement=placement,
    )


__all__ = ["Bound", "Endpoint", "bind", "dom_id_for", "endpoint_for"]
