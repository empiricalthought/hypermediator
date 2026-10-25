"""Template tags that render bound affordances as the Rendered HTML Contract.

Python builds each control's context; the overridable ``hypermediator/*.html`` templates
produce the markup."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal, cast

from django import template
from django.db.models import Model
from django.forms import BaseForm, BoundField, ChoiceField, ModelChoiceField
from django.forms.models import ModelMultipleChoiceField
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.utils.html import format_html
from django.utils.safestring import SafeString

from hypermediator.affordances import Placement
from hypermediator.endpoints import Bound, bind
from hypermediator.htmx import HTMX_SHA256
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


def _page_override(request: HttpRequest, attr: str, url_name: str) -> Any:
    """What the page's own view declares in its ``attr`` mapping (``placements`` or
    ``link_headers``) for ``url_name``, if anything."""
    match = request.resolver_match
    if match is None:
        return None
    view_class = getattr(match.func, "view_class", None)
    if isinstance(view_class, type) and issubclass(view_class, HypermediaMixin):
        return getattr(view_class, attr).get(url_name)
    declaration = getattr(match.func, "hypermediator", None)
    return None if declaration is None else getattr(declaration, attr).get(url_name)


def _placement_override(request: HttpRequest, url_name: str) -> Placement | None:
    override: Placement | None = _page_override(request, "placements", url_name)
    return override


def _link_header_override(request: HttpRequest, url_name: str) -> bool | None:
    override: bool | None = _page_override(request, "link_headers", url_name)
    return override


def _hx(bound: Bound, verb: Literal["hx-get", "hx-post"]) -> dict[str, str]:
    """The htmx attributes of an enabled control; a disabled one has none."""
    if bound.state != "enabled":
        return {}
    placement = bound.placement
    hx = {verb: bound.url, "hx-target": placement.target, "hx-swap": placement.swap}
    key = None if bound.obj is None else item_key(bound.obj)
    if placement.select == "item":
        if key is not None:
            css_key = key.replace("\\", "\\\\").replace('"', '\\"')
            hx["hx-select"] = f'[data-hm-item="{css_key}"]'
    elif placement.select is not None:
        hx["hx-select"] = placement.select
    if placement.push_url:
        hx["hx-push-url"] = "true"
    if bound.endpoint.affordance.trigger:
        hx["hx-trigger"] = bound.endpoint.affordance.trigger
    if placement == Placement.ITEM and key is not None:
        hx["hx-headers"] = json.dumps({"HX-Hm-Item": key})
    return hx


def _render(
    template_name: str,
    request: HttpRequest,
    bound: Bound,
    element: Literal["a", "form"],
    **extra: Any,
) -> SafeString:
    """Render a control template with the public template context.

    These variables are public API; templates that override ``hypermediator/*.html`` may rely
    on them, and they are not renamed without a major version:

    - ``bound``: the bound affordance. ``bound.dom_id`` (the wrapper id), ``bound.reason``
      (why it is disabled, empty when enabled), ``bound.url``, ``bound.state`` (``"enabled"``
      or ``"disabled"``; hidden controls are never rendered) and ``bound.endpoint.name``.
    - ``label``: the affordance's label.
    - ``rels``: all rel tokens, for the microdata.
    - ``html_rel``: the rel tokens valid on the element, space-joined (``""`` when none).
    - ``hx``: a dict of htmx attributes (empty when disabled).
    - ``itemtype``: the microdata item type.
    - ``form`` and ``rows``: for ``form.html`` only; the form and its ``(field, current)`` pairs.
    """
    affordance = bound.endpoint.affordance
    return render_to_string(
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


def _record(request: HttpRequest, bound: Bound) -> None:
    rendered: list[Bound] | None = getattr(request, "_hm_rendered", None)
    if rendered is None:
        rendered = []
        request._hm_rendered = rendered  # type: ignore[attr-defined]
    rendered.append(bound)


def _bind_and_record(request: HttpRequest, url_name: str, obj: Model | None) -> Bound | None:
    bound = bind(
        request,
        url_name,
        obj,
        placement_override=_placement_override(request, url_name),
        link_header_override=_link_header_override(request, url_name),
    )
    if bound.state == "hidden":
        return None
    _record(request, bound)
    return bound


def _form_hx(bound: Bound) -> dict[str, str]:
    """A full form always targets itself; a disabled one carries no htmx attributes."""
    if bound.state != "enabled":
        return {}
    selector = f"#{bound.dom_id}"
    return {
        "hx-post": bound.url,
        "hx-target": selector,
        "hx-swap": "outerHTML",
        "hx-select": selector,
    }


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


def _readable(field: BoundField, stored: Any) -> str:
    """``stored`` as the user would read it: related objects' text and choice labels."""
    form_field = field.field
    if isinstance(form_field, ModelChoiceField | ModelMultipleChoiceField):
        pks = stored if isinstance(stored, list) else [] if stored is None else [stored]
        queryset = form_field.queryset
        objects = [] if queryset is None else queryset.filter(pk__in=pks)
        return ", ".join(str(o) for o in objects)
    if isinstance(form_field, ChoiceField):
        labels = {str(value): str(label) for value, label in cast(Any, form_field.choices)}
        values = stored if isinstance(stored, list) else [stored]
        return ", ".join(labels.get(str(v), str(v)) for v in values if v is not None)
    prepared = form_field.prepare_value(stored)
    return "" if prepared is None else str(prepared)


def _current_value(field: BoundField, current: Mapping[str, Any] | None) -> str | None:
    """The stored value of ``field``, readable, when it differs from the submitted one."""
    if not current or not field.form.is_bound or field.name not in current:
        return None
    stored = current[field.name]
    if not field.field.has_changed(stored, field.data):
        return None
    return _readable(field, stored)


@register.simple_tag(takes_context=True)
def hm_form(
    context: template.Context, url_name: str, form: BaseForm, obj: Model | None = None
) -> SafeString | str:
    request = _request(context)
    bound = _bind_and_record(request, url_name, obj)
    if bound is None:
        return ""
    rows = [
        (field, _current_value(field, context.get("hm_current"))) for field in form.visible_fields()
    ]
    return _render(
        "hypermediator/form.html", request, bound, "form", form=form, rows=rows, hx=_form_hx(bound)
    )


@register.simple_tag
def hm_item(obj: Model) -> SafeString:
    return format_html(' data-hm-item="{}"', item_key(obj))


@register.simple_tag
def hm_htmx() -> SafeString:
    """The ``<script>`` tag for the vendored, pinned htmx, with its integrity hash."""
    return render_to_string("hypermediator/htmx.html", {"integrity": HTMX_SHA256})
