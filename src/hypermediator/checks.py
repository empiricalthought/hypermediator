"""System checks: where a view's declarations and its Django handlers disagree."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.apps import AppConfig
from django.core.checks import CheckMessage, Error, Tags, Warning, register

from hypermediator.endpoints import _allowed_methods, url_routes
from hypermediator.lint import lint_files
from hypermediator.views import FunctionDeclaration, HypermediaMixin

_NOT_HANDLERS = frozenset({"HEAD", "OPTIONS"})
_W001_HINT = (
    'Set http_method_names = ["get", "post", "head", "options"] on the view, '
    "or declare an affordance for these methods."
)


def _handlers(view_class: type) -> frozenset[str]:
    """The methods Django lists in Allow for this view."""
    names: tuple[str, ...] = getattr(view_class, "http_method_names", ())
    return frozenset(m.upper() for m in names if hasattr(view_class, m)) - _NOT_HANDLERS


@register(Tags.urls)
def check_declarations(
    app_configs: Iterable[AppConfig] | None = None, **kwargs: Any
) -> list[CheckMessage]:
    messages: list[CheckMessage] = []
    for url_name, pattern in url_routes():
        callback = pattern.callback
        view_class: type | None = getattr(callback, "view_class", None)
        declaration: FunctionDeclaration | None = getattr(callback, "hypermediator", None)
        if declaration is not None:
            obj: object = callback
        elif view_class is not None and issubclass(view_class, HypermediaMixin):
            obj = view_class
        else:
            continue
        label = url_name or str(pattern.pattern)
        if url_name is None:
            messages.append(
                Error(
                    f"{_describe(obj)} is routed at '{label}' without a URL name.",
                    hint="Give the path() a name=; affordances are looked up by URL name.",
                    obj=obj,
                    id="hypermediator.E001",
                )
            )
        if declaration is not None:
            if declaration.unavailable is not None and declaration.model is None:
                messages.append(
                    Error(
                        f"{_describe(obj)} ('{label}') declares unavailable= but no model=.",
                        hint="Pass model= so the unavailable check receives the object.",
                        obj=obj,
                        id="hypermediator.E002",
                    )
                )
        elif view_class is not None:
            messages.extend(_check_view_class(view_class, label))
    return messages


def _describe(obj: object) -> str:
    return getattr(obj, "__qualname__", repr(obj))


def _check_view_class(view_class: type, label: str) -> list[CheckMessage]:
    messages: list[CheckMessage] = []
    declares = getattr(view_class, "affordance", None) is not None
    declared = _allowed_methods(view_class) if declares else frozenset({"GET"})
    extra = _handlers(view_class) - declared
    if extra:
        messages.append(
            Warning(
                f"{view_class.__qualname__} ('{label}') handles {', '.join(sorted(extra))} "
                "but its affordances do not declare it.",
                hint=_W001_HINT,
                obj=view_class,
                id="hypermediator.W001",
            )
        )
    has_fields = (
        getattr(view_class, "form_class", None) is not None
        or getattr(view_class, "fields", None) is not None
    )
    if declares and has_fields and not hasattr(view_class, "post"):
        messages.append(
            Warning(
                f"{view_class.__qualname__} ('{label}') declares an affordance with form "
                "fields but has no post handler.",
                hint="Add a post() handler, or remove the fields from the affordance's view.",
                obj=view_class,
                id="hypermediator.W002",
            )
        )
    return messages


@register("hypermediator_templates")
def check_templates(
    app_configs: Iterable[AppConfig] | None = None, **kwargs: Any
) -> list[CheckMessage]:
    """Report hand-written links and forms to affordances; never an error."""
    return [
        Warning(issue.message, obj=str(path), id="hypermediator.W101")
        for path, issue in lint_files()
    ]
