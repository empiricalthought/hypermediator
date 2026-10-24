from collections.abc import Callable

import pytest
from django.contrib.auth.models import Permission, User
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from django.template import engines
from django.test import RequestFactory
from django.urls import resolve

from hypermediator.middleware import HypermediatorMiddleware
from tests.models import Widget

pytestmark = pytest.mark.django_db


def run(
    source: str,
    *,
    can_change: bool = False,
    headers: dict[str, str] | None = None,
    status: int = 200,
    streaming: bool = False,
    existing_link: str | None = None,
    path: str = "/",
    **context: object,
) -> HttpResponseBase:
    request = RequestFactory().get(path, headers=headers)
    if path != "/":
        request.resolver_match = resolve(path)
    user = User.objects.create_user(f"u{User.objects.count()}", password="pw")
    if can_change:
        user.user_permissions.add(Permission.objects.get(codename="change_widget"))
    request.user = user

    def get_response(request: HttpRequest) -> HttpResponseBase:
        template = engines["django"].from_string("{% load hypermediator %}" + source)
        body = template.render({"request": request, **context})
        response: HttpResponseBase
        if streaming:
            response = StreamingHttpResponse([body], status=status)
        else:
            response = HttpResponse(body, status=status)
        if existing_link:
            response.headers["Link"] = existing_link
        return response

    middleware: Callable[[HttpRequest], HttpResponseBase] = HypermediatorMiddleware(get_response)
    return middleware(request)


def test_link_header_lists_enabled_only() -> None:
    widget = Widget.objects.create(name="w")
    source = (
        "{% hm_link 'widget-renew' w %}{% hm_link 'widget-renew' w %}{% hm_link 'widget-next' %}"
    )
    enabled = run(source, can_change=True, w=widget)
    assert enabled.headers["Link"] == (
        f'</widget/{widget.pk}/renew/>; rel="edit", </widgets/next/>; rel="next edit '
        'https://example.com/rel/x"'
    )
    denied = run("{% hm_link 'widget-renew' w %}", w=widget)
    assert "Link" not in denied.headers


def test_link_header_quotes_uri_rels() -> None:
    response = run("{% hm_link 'widget-next' %}")
    assert response.headers["Link"] == (
        '</widgets/next/>; rel="next edit https://example.com/rel/x"'
    )


def test_link_header_appends_to_existing() -> None:
    response = run("{% hm_link 'widget-next' %}", existing_link='<https://a.example/>; rel="up"')
    assert response.headers["Link"].startswith('<https://a.example/>; rel="up", </widgets/next/>;')


def test_unselected_affordance_adds_no_link_header() -> None:
    response = run("{% hm_link 'widget-quiet' %}")
    assert "Link" not in response.headers


def test_selected_affordance_is_in_link_header() -> None:
    response = run("{% hm_link 'widget-quiet' %}", path="/widgets/page/")
    assert response.headers["Link"] == '</widgets/quiet/>; rel="help"'


@pytest.mark.parametrize("path", ["/widgets/page/", "/widgets/page-fn/"])
def test_page_override_turns_selection_off(path: str) -> None:
    widget = Widget.objects.create(name="w")
    source = "{% hm_link 'widget-renew' w %}"
    assert "Link" in run(source, can_change=True, w=widget).headers
    assert "Link" not in run(source, can_change=True, w=widget, path=path).headers


@pytest.mark.parametrize("path", ["/widgets/page/", "/widgets/page-fn/"])
def test_page_override_turns_selection_on(path: str) -> None:
    response = run("{% hm_link 'widget-quiet' %}", path=path)
    assert response.headers["Link"] == '</widgets/quiet/>; rel="help"'


def test_disabled_selected_affordance_is_not_in_link_header() -> None:
    widget = Widget.objects.create(name="w", status="retired")
    response = run("{% hm_link 'widget-renew' w %}", can_change=True, w=widget)
    assert "disabled" in response.content.decode()  # type: ignore[attr-defined]
    assert "Link" not in response.headers


def test_reswap_none_when_item_missing() -> None:
    widget = Widget.objects.create(name="w")
    headers = {"HX-Request": "true", "HX-Hm-Item": f"tests.widget:{widget.pk}"}
    response = run("<p>nothing</p>", headers=headers)
    assert response.headers["HX-Reswap"] == "none"


def test_no_reswap_when_item_present() -> None:
    widget = Widget.objects.create(name="w")
    headers = {"HX-Request": "true", "HX-Hm-Item": f"tests.widget:{widget.pk}"}
    response = run("<li{% hm_item w %}>x</li>", headers=headers, w=widget)
    assert "HX-Reswap" not in response.headers


@pytest.mark.parametrize(
    ("headers", "status", "streaming"),
    [
        ({"HX-Hm-Item": "tests.widget:1"}, 200, False),
        ({"HX-Request": "true"}, 200, False),
        ({"HX-Request": "true", "HX-Hm-Item": "tests.widget:1"}, 422, False),
        ({"HX-Request": "true", "HX-Hm-Item": "tests.widget:1"}, 200, True),
    ],
)
def test_no_reswap_unless_conditions_hold(
    headers: dict[str, str], status: int, streaming: bool
) -> None:
    response = run("<p>x</p>", headers=headers, status=status, streaming=streaming)
    assert "HX-Reswap" not in response.headers
