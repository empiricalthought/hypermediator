"""Layer verification: assert that a rendered page conforms to PRINCIPLES.md layers 1 to 4."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Literal, cast

from django.apps import apps
from django.db.models import Count, Max, Model
from django.http import HttpResponse
from django.http.response import HttpResponseBase
from django.test import Client

from hypermediator.endpoints import endpoint_for
from hypermediator.extract import Control, Page, extract
from hypermediator.rels import html_rels

_IMPLICIT_METHODS = frozenset({"HEAD", "OPTIONS"})
_HX_TAGS_CHECKED_AS_CONTROLS = frozenset({"a", "form"})
_FORM_PARTS = frozenset({"button", "input", "select", "textarea"})
_FORBIDDEN_HX = frozenset({"hx-put", "hx-patch", "hx-delete"})
_REQUIRED_VARY = ("HX-Request", "HX-Request-Type")


def _page_of(response: HttpResponseBase) -> Page:
    # The test client's responses are typed as HttpResponseBase; they carry content.
    body = cast(HttpResponse, response)
    return extract(body.content.decode(body.charset))


def _is_managed(control: Control) -> bool:
    return control.name is not None


def _is_anchor_target(control: Control) -> bool:
    """A plain ``<a id>`` target: no href and neither disabled-link marker, so not a control."""
    return (
        control.kind == "link"
        and control.href is None
        and control.attrs.get("aria-disabled") != "true"
        and control.attrs.get("role") != "link"
    )


def _ref(control: Control) -> str:
    return control.id or control.href or control.label or control.kind


def _layer1(controls: list[Control]) -> list[str]:
    found: list[str] = []
    for control in controls:
        if control.kind == "form" and not control.href:
            found.append(f"L1: form '{_ref(control)}' has no action")
        elif control.enabled and not control.href:
            found.append(f"L1: enabled control '{_ref(control)}' has no href")
        if control.kind == "form" and control.method not in ("GET", "POST"):
            found.append(f"L1: form '{_ref(control)}' uses method '{control.method}'")
    return found


def _layer2(page: Page, controls: list[Control]) -> list[str]:
    found: list[str] = []
    for control in controls:
        if not control.label:
            found.append(f"L2: control '{_ref(control)}' has no accessible name")
        for field in control.fields:
            if not field.label:
                found.append(
                    f"L2: field '{field.name}' of control '{_ref(control)}' has no accessible name"
                )
        if not control.enabled and not control.reason:
            found.append(f"L2: disabled control '{_ref(control)}' has no reason")
    found.extend(f"L2: duplicate id '{i}'" for i, n in page.ids.items() if n > 1)
    return found


def _layer3(page: Page, controls: list[Control]) -> list[str]:
    found: list[str] = []
    for control in controls:
        element: Literal["a", "form"] = "a" if control.kind == "link" else "form"
        valid = set(html_rels(control.element_rel, element))
        found.extend(
            f"L3: rel '{token}' is not valid on <{element}> '{_ref(control)}'"
            for token in control.element_rel
            if token not in valid
        )
        # Only the wrapper's own control needs the microdata; application links inside a
        # managed form (a help_text link, say) are not affordances.
        own = control.wrapper_id is not None and control.id == f"{control.wrapper_id}-c"
        if control.name is None and own:
            found.append(
                f"L3: control '{_ref(control)}' in wrapper '{control.wrapper_id}' has no "
                "microdata item whose control resolves to it"
            )
    for item in page.microdata:
        where = f"wrapper '{item.wrapper_id}'" if item.wrapper_id else "page"
        if not any(item.props.get("name", ())):
            found.append(f"L3: microdata item in {where} has no name")
        targets = item.props.get("control", ())
        if not targets:
            found.append(f"L3: microdata item in {where} has no control")
        found.extend(
            f"L3: microdata control '{t}' in {where} is not an id on the page"
            for t in targets
            if t not in page.ids
        )
    return found


def _layer4(page: Page, controls: list[Control], response: HttpResponseBase) -> list[str]:
    found: list[str] = []
    for control in controls:
        if control.hx and not control.enabled:
            attrs = ", ".join(sorted(control.hx))
            found.append(f"L4: control '{_ref(control)}' carries {attrs} but has no href or action")
    for tag, hx_attrs, contains_native, in_form in page.hx_elements:
        names = ", ".join(sorted(hx_attrs))
        for verb in sorted(_FORBIDDEN_HX & set(hx_attrs)):
            found.append(f"L4: <{tag}> carries {verb}; only GET and POST are allowed")
        if tag in _FORM_PARTS:
            if not in_form:
                found.append(f"L4: <{tag}> carries {names} outside a form with an action")
        elif tag not in _HX_TAGS_CHECKED_AS_CONTROLS and not contains_native:
            found.append(f"L4: <{tag}> carries {names} without a native control")
    if any(_is_managed(c) for c in controls):
        vary = {v.strip().lower() for v in response.headers.get("Vary", "").split(",")}
        for required in _REQUIRED_VARY:
            if required.lower() not in vary:
                found.append(
                    f"L4: Vary lacks {required} (got '{response.headers.get('Vary', '')}')"
                )
    return found


def violations(response: HttpResponseBase) -> list[str]:
    """One message per failed layer 1 to 4 rule, each starting with its layer tag."""
    page = _page_of(response)
    # hx-* on a plain anchor is still a violation, so L4 sees every control.
    real = [c for c in page.controls if not _is_anchor_target(c)]
    return [
        *_layer1(real),
        *_layer2(page, real),
        *_layer3(page, real),
        *_layer4(page, list(page.controls), response),
    ]


def assert_conforms(response: HttpResponseBase) -> Page:
    """Raise ``AssertionError`` listing every violation, else return the extracted page."""
    found = violations(response)
    if found:
        raise AssertionError("Page does not conform:\n" + "\n".join(f"- {v}" for v in found))
    return _page_of(response)


def _state_of(control: Control) -> str:
    return "enabled" if control.enabled else "disabled"


def assert_same_affordances(full: HttpResponseBase, fragment: HttpResponseBase) -> None:
    """The fragment exposes the same (name, state) multiset as the full page's matching region."""
    fragment_page = _page_of(fragment)
    full_page = _page_of(full)
    expected = Counter((c.name, _state_of(c)) for c in fragment_page.controls if _is_managed(c))
    roots = set(fragment_page.root_ids)
    if not roots:
        raise AssertionError("fragment root has no id; cannot locate its region in the full page")
    actual = Counter(
        (c.name, _state_of(c))
        for c in full_page.controls
        if _is_managed(c) and (c.wrapper_id in roots or roots & set(c.ancestor_ids))
    )
    if expected != actual:
        raise AssertionError(
            f"Fragment affordances {sorted(expected.elements(), key=str)} differ from the "
            f"full page's {sorted(actual.elements(), key=str)} in the same region"
        )


def assert_allow_matches(client: Client, path: str, url_name: str) -> None:
    """``Allow`` (less HEAD and OPTIONS) equals the endpoint's declared methods."""
    endpoint = endpoint_for(url_name)
    if endpoint is None:
        raise AssertionError(f"The view named {url_name!r} declares no affordance")
    header = client.options(path).headers.get("Allow", "")
    allowed = {m.strip() for m in header.split(",") if m.strip()} - _IMPLICIT_METHODS
    declared = endpoint.methods - _IMPLICIT_METHODS
    if allowed != declared:
        raise AssertionError(
            f"Allow for {path} is {sorted(allowed)}; {url_name!r} declares {sorted(declared)}"
        )


def _snapshot(exclude: frozenset[type[Model]]) -> dict[str, tuple[int, object]]:
    snapshot: dict[str, tuple[int, object]] = {}
    for model in apps.get_models():
        if model in exclude or not model._meta.managed or model._meta.proxy:
            continue
        totals = model._default_manager.aggregate(count=Count("pk"), top=Max("pk"))
        snapshot[model._meta.label] = (totals["count"], totals["top"])
    return snapshot


def assert_get_does_not_change_state(
    client: Client, path: str, *, exclude: Iterable[type[Model]] = ()
) -> HttpResponseBase:
    """A GET succeeds and leaves every model's row count and highest pk unchanged.

    Models in ``exclude`` are not snapshotted, for state a GET legitimately writes, such as
    the session."""
    skipped = frozenset(exclude)
    before = _snapshot(skipped)
    response = client.get(path)
    after = _snapshot(skipped)
    if response.status_code >= 400:
        raise AssertionError(f"GET {path} returned {response.status_code}")
    changed = [
        f"{label}: {before[label]} -> {after[label]}"
        for label in before
        if before[label] != after[label]
    ]
    if changed:
        raise AssertionError(f"GET {path} changed state:\n" + "\n".join(changed))
    return response
