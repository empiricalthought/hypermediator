import dataclasses
import json
from html.parser import HTMLParser

import pytest
from django import forms
from django.contrib.auth.models import AnonymousUser, Permission, User
from django.http import HttpRequest
from django.template import engines
from django.test import Client, RequestFactory
from django.urls import resolve

from hypermediator.endpoints import Bound, bind
from hypermediator.extract import Control, extract
from hypermediator.templatetags.hypermediator import _hx
from tests.models import Widget
from tests.views import OVERRIDE, RenewForm

pytestmark = pytest.mark.django_db


def make_request(
    *, can_change: bool = False, path: str = "/", anonymous: bool = False
) -> HttpRequest:
    request = RequestFactory().get(path)
    if anonymous:
        request.user = AnonymousUser()
    else:
        user = User.objects.create_user(f"u{User.objects.count()}", password="pw")
        if can_change:
            user.user_permissions.add(Permission.objects.get(codename="change_widget"))
        request.user = user
    if path != "/":
        request.resolver_match = resolve(path)
    return request


def render(source: str, request: HttpRequest, **context: object) -> str:
    template = engines["django"].from_string("{% load hypermediator %}" + source)
    return template.render({"request": request, **context})


def only(html: str, name: str) -> Control:
    (control,) = extract(html).by_name(name)
    return control


@pytest.fixture
def widget() -> Widget:
    return Widget.objects.create(name="w")


def test_link_states(widget: Widget) -> None:
    retired = Widget.objects.create(name="r", status="retired")
    source = "{% hm_link 'widget-renew' w %}"
    editor = make_request(can_change=True)
    enabled = only(render(source, editor, w=widget), "widget-renew")
    assert enabled.enabled
    assert enabled.href == f"/widget/{widget.pk}/renew/"
    assert enabled.label == "Renew"
    assert enabled.wrapper_id == f"hm-widget-renew-{widget.pk}"
    disabled = only(render(source, editor, w=retired), "widget-renew")
    assert not disabled.enabled
    assert disabled.href is None
    assert disabled.reason == "Retired widgets cannot be renewed"
    assert disabled.hx == {}
    assert render(source, make_request(), w=widget) == ""
    assert extract(render(source, make_request(), w=widget)).controls == ()


def test_link_rel_split() -> None:
    html = render("{% hm_link 'widget-next' %}", make_request())
    control = only(html, "widget-next")
    assert 'rel="next"' in html
    assert 'rel="edit' not in html
    assert set(control.rel) == {"next", "edit", "https://example.com/rel/x"}
    assert "https://example.com/rel/x" in html.split("<span hidden")[1]
    anchor = html.split("<a ")[1].split(">")[0]
    assert "edit" not in anchor
    assert "example.com" not in anchor


def test_action_button_disabled(widget: Widget) -> None:
    retired = Widget.objects.create(name="r", status="retired")
    source = "{% hm_action 'widget-renew' w %}"
    editor = make_request(can_change=True)
    enabled = only(render(source, editor, w=widget), "widget-renew")
    assert (enabled.kind, enabled.method, enabled.enabled) == ("form", "POST", True)
    assert enabled.href == f"/widget/{widget.pk}/renew/"
    assert enabled.hx["hx-post"] == enabled.href
    html = render(source, editor, w=retired)
    assert "csrfmiddlewaretoken" in html
    disabled = only(html, "widget-renew")
    assert not disabled.enabled
    assert disabled.reason == "Retired widgets cannot be renewed"
    assert disabled.label == "Renew"
    assert disabled.hx == {}
    assert render(source, make_request(), w=widget) == ""


def test_form_renders_errors_described_and_422_context() -> None:
    client = Client()
    response = client.post("/renew-form/", {"renewal_date": "nope"})
    assert response.status_code == 422
    html = response.content.decode()
    control = only(html, "renew-form")
    assert control.hx["hx-target"] == "#hm-renew-form"
    assert control.hx["hx-swap"] == "outerHTML"
    assert control.hx["hx-select"] == "#hm-renew-form"
    assert control.label == "Renew book"
    (field,) = control.fields
    assert "id_renewal_date_error" in field.described_by
    assert extract(html).ids["id_renewal_date_error"] == 1
    assert 'name="csrfmiddlewaretoken"' in html


def test_form_non_field_errors_and_hidden_fields() -> None:
    class Hidden(RenewForm):
        _hm_fingerprint = forms.CharField(widget=forms.HiddenInput, required=False)

        def clean(self) -> dict[str, object]:
            raise forms.ValidationError("Whole form is wrong")

    form = Hidden({"renewal_date": "2026-01-01", "_hm_fingerprint": "abc"})
    assert not form.is_valid()
    html = render("{% hm_form 'renew-form' form %}", make_request(), form=form)
    page = extract(html)
    assert 'id="hm-renew-form-errors" role="alert"' in html
    assert "Whole form is wrong" in page.text_by_id["hm-renew-form-errors"]
    assert '<input type="hidden" name="_hm_fingerprint"' in html
    assert [f.name for f in only(html, "renew-form").fields] == ["renewal_date"]


def test_item_placement_attrs(widget: Widget) -> None:
    key = f"tests.widget:{widget.pk}"
    editor = make_request(can_change=True)
    link = only(render("{% hm_link 'widget-renew' w %}", editor, w=widget), "widget-renew")
    assert link.hx["hx-get"] == link.href
    assert link.hx["hx-target"] == "closest [data-hm-item]"
    assert link.hx["hx-swap"] == "outerHTML"
    assert link.hx["hx-select"] == f'[data-hm-item="{key}"]'
    assert link.hx["hx-headers"] == f'{{"HX-Hm-Item": "{key}"}}'
    assert "hx-push-url" not in link.hx
    assert render("<li{% hm_item w %}>", editor, w=widget) == f'<li data-hm-item="{key}">'


def test_page_placement_attrs() -> None:
    link = only(render("{% hm_link 'widget-next' %}", make_request()), "widget-next")
    assert link.hx["hx-target"] == "body"
    assert link.hx["hx-swap"] == "innerHTML"
    assert link.hx["hx-select"] == "body"
    assert link.hx["hx-push-url"] == "true"
    assert "hx-headers" not in link.hx


@pytest.mark.parametrize("path", ["/widgets/page/", "/widgets/page-fn/"])
def test_placement_override_from_referencing_view(widget: Widget, path: str) -> None:
    request = make_request(can_change=True, path=path)
    link = only(render("{% hm_link 'widget-renew' w %}", request, w=widget), "widget-renew")
    assert link.hx["hx-target"] == OVERRIDE.target
    assert link.hx["hx-swap"] == "innerHTML"
    assert link.hx["hx-select"] == "#panel"
    assert "hx-headers" not in link.hx


class _Microdata(HTMLParser):
    """A minimal walk: the properties each itemscope owns directly."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, int | None]] = []
        self.scopes: list[tuple[str, list[str]]] = []
        self._open: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        scope: int | None = None
        if "itemscope" in a:
            self.scopes.append((a.get("itemtype") or "", []))
            scope = len(self.scopes) - 1
        if "itemprop" in a and self._open:
            self.scopes[self._open[-1]][1].append(a["itemprop"] or "")
        if tag != "meta":
            self.stack.append((tag, scope))
            if scope is not None:
                self._open.append(scope)

    def handle_endtag(self, tag: str) -> None:
        if self.stack and self.stack[-1][0] == tag:
            _, scope = self.stack.pop()
            if scope is not None:
                self._open.pop()


def test_microdata_does_not_capture_app_props(widget: Widget) -> None:
    source = (
        '<div itemscope itemtype="https://schema.org/Book">'
        '<span itemprop="name">{% hm_link "widget-renew" w %}</span></div>'
    )
    html = render(source, make_request(can_change=True), w=widget)
    walker = _Microdata()
    walker.feed(html)
    book = [props for itemtype, props in walker.scopes if itemtype.endswith("Book")]
    assert book == [["name"]]
    ours = [
        props for itemtype, props in walker.scopes if itemtype == "urn:hypermediator:Affordance"
    ]
    assert ours == [["name", "control", "rel"]]


def test_rendered_recorded_on_request(widget: Widget) -> None:
    retired = Widget.objects.create(name="r", status="retired")
    request = make_request(can_change=True)
    render(
        "{% hm_link 'widget-renew' w %}{% hm_link 'widget-renew' r %}", request, w=widget, r=retired
    )
    rendered: list[Bound] = request._hm_rendered  # type: ignore[attr-defined]
    assert [b.state for b in rendered] == ["enabled", "disabled"]
    hidden_request = make_request()
    render("{% hm_link 'widget-renew' w %}", hidden_request, w=widget)
    assert getattr(hidden_request, "_hm_rendered", []) == []


def test_disabled_form_has_no_hx_and_describes_button() -> None:
    Widget.objects.create(name="f", status="full")
    html = render("{% hm_form 'widget-create' form %}", make_request(), form=RenewForm())
    control = only(html, "widget-create")
    assert not control.enabled
    assert control.hx == {}
    assert control.reason == "Creation is closed"
    assert 'aria-describedby="hm-widget-create-reason"' in html
    assert 'rel="' not in html.split("<form")[1].split(">")[0]


def test_enabled_form_has_no_rel_attribute() -> None:
    html = render("{% hm_form 'renew-form' form %}", make_request(), form=RenewForm())
    assert "rel=" not in html.split("<form")[1].split(">")[0]


def test_hx_values_are_escaped_for_json_and_css(widget: Widget) -> None:
    bound = bind(make_request(can_change=True), "widget-renew", widget)
    nasty = dataclasses.replace(bound, obj=Widget(pk='a"b\\c'))
    hx = _hx(nasty, "hx-get")
    key = 'tests.widget:a"b\\c'
    assert json.loads(hx["hx-headers"]) == {"HX-Hm-Item": key}
    assert hx["hx-select"] == '[data-hm-item="tests.widget:a\\"b\\\\c"]'


def test_label_and_reason_are_escaped() -> None:
    html = render("{% hm_link 'widget-odd' %}", make_request())
    assert "<b>" not in html
    control = only(html, "widget-odd")
    assert control.label == "<b>\"&'"
    assert control.reason == "<b>\"&'"
