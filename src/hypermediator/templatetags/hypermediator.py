"""Template tags that render bound affordances as the Rendered HTML Contract.

Python builds each control's context; the overridable ``hypermediator/*.html`` templates
produce the markup."""

from __future__ import annotations

from typing import Any, Literal

from django import template
from django.db.models import Model
from django.forms import BaseForm
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import SafeString

from hypermediator.affordances import Placement
from hypermediator.endpoints import Bound, bind
from hypermediator.microdata import ITEMTYPE
from hypermediator.rels import html_rels
from hypermediator.views import HypermediaMixin

register = template.Library()


def item_key(obj: Model) -> str:
    """The value of ``data-hm-item`` for ``obj``."""
    return f"{obj._meta.app_label}.{obj._meta.model_name}:{obj.pk}"


def _request(context: template.Context) -> HttpRequest:
    request: HttpRequest | None = getattr(context, "request", None) or context.get("request")
    if request is None:
        raise template.TemplateSyntaxError("hypermediator tags need the request in the context")
    return request


def _placement_override(request: HttpRequest, url_name: str) -> Placement | None:
    """The placement the page's own view declares for ``url_name``, if any."""
    match = request.resolver_match
    if match is None:
        return None
    view_class = getattr(match.func, "view_class", None)
    if isinstance(view_class, type) and issubclass(view_class, HypermediaMixin):
        return view_class.placements.get(url_name)
    declaration = getattr(match.func, "hypermediator", None)
    return None if declaration is None else declaration.placements.get(url_name)


def _hx(bound: Bound, verb: Literal["hx-get", "hx-post"]) -> dict[str, str]:
    """The htmx attributes of an enabled control; a disabled one has none."""
    if bound.state != "enabled":
        return {}
    placement = bound.placement
    hx = {verb: bound.url, "hx-target": placement.target, "hx-swap": placement.swap}
    key = None if bound.obj is None else item_key(bound.obj)
    if placement.select == "item":
        if key is not None:
            hx["hx-select"] = f'[data-hm-item="{key}"]'
    elif placement.select is not None:
        hx["hx-select"] = placement.select
    if placement.push_url:
        hx["hx-push-url"] = "true"
    if bound.endpoint.affordance.trigger:
        hx["hx-trigger"] = bound.endpoint.affordance.trigger
    if placement == Placement.ITEM and key is not None:
        hx["hx-headers"] = f'{{"HX-Hm-Item": "{key}"}}'
    return hx


def _render(
    template_name: str,
    request: HttpRequest,
    bound: Bound,
    element: Literal["a", "form"],
    **extra: Any,
) -> SafeString:
    affordance = bound.endpoint.affordance
    return SafeString(
        render_to_string(
            template_name,
            {
                "bound": bound,
                "label": affordance.label,
                "rels": affordance.rel,
                "html_rel": " ".join(html_rels(affordance.rel, element)),
                "itemtype": ITEMTYPE,
                **extra,
            },
            request=request,
        )
    )


def _record(request: HttpRequest, bound: Bound) -> None:
    rendered: list[Bound] | None = getattr(request, "_hm_rendered", None)
    if rendered is None:
        rendered = []
        request._hm_rendered = rendered  # type: ignore[attr-defined]
    rendered.append(bound)


def _bind_and_record(request: HttpRequest, url_name: str, obj: Model | None) -> Bound | None:
    bound = bind(request, url_name, obj, placement_override=_placement_override(request, url_name))
    if bound.state == "hidden":
        return None
    _record(request, bound)
    return bound


def render_link(request: HttpRequest, bound: Bound) -> SafeString:
    """The link control (wrapper, link or disabled link, reason, microdata) for ``bound``."""
    return _render("hypermediator/link.html", request, bound, "a", hx=_hx(bound, "hx-get"))


@register.simple_tag(takes_context=True)
def hm_link(context: template.Context, url_name: str, obj: Model | None = None) -> SafeString | str:
    request = _request(context)
    bound = _bind_and_record(request, url_name, obj)
    return "" if bound is None else render_link(request, bound)


@register.simple_tag(takes_context=True)
def hm_action(
    context: template.Context, url_name: str, obj: Model | None = None
) -> SafeString | str:
    request = _request(context)
    bound = _bind_and_record(request, url_name, obj)
    if bound is None:
        return ""
    return _render("hypermediator/action.html", request, bound, "form", hx=_hx(bound, "hx-post"))


@register.simple_tag(takes_context=True)
def hm_form(
    context: template.Context, url_name: str, form: BaseForm, obj: Model | None = None
) -> SafeString | str:
    request = _request(context)
    bound = _bind_and_record(request, url_name, obj)
    if bound is None:
        return ""
    return _render("hypermediator/form.html", request, bound, "form", form=form)


@register.simple_tag
def hm_item(obj: Model) -> SafeString:
    return format_html(' data-hm-item="{}"', item_key(obj))
