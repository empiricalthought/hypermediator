import pytest
from django.contrib.auth.models import Permission, User
from django.http import HttpResponse
from django.test import Client

from hypermediator.htmx import redirect_to_location
from tests.models import Widget

HX = {"HX-Request": "true"}
PARTIAL = {"HX-Request": "true", "HX-Request-Type": "partial"}


def test_invalid_form_is_422_cbv_and_fbv(client: Client) -> None:
    assert client.post("/pipeline/cbv/", {}).status_code == 422
    assert client.post("/pipeline/fbv/", {}).status_code == 422


def test_valid_get_is_200(client: Client) -> None:
    assert client.get("/pipeline/cbv/").status_code == 200
    assert client.get("/pipeline/fbv/").status_code == 200


def test_partial_rendered_for_partial_request(client: Client) -> None:
    for url in ("/pipeline/cbv/", "/pipeline/fbv/"):
        body = client.get(url, headers=PARTIAL).content.decode()
        assert body.startswith('<form id="f">')
        assert "<html>" not in body
        assert "<html>" in client.get(url).content.decode()


def test_vary_header(client: Client) -> None:
    for url in ("/pipeline/cbv/", "/pipeline/fbv/"):
        vary = {v.strip() for v in client.get(url)["Vary"].split(",")}
        assert {"HX-Request", "HX-Request-Type"} <= vary


def test_page_placement_redirect_becomes_hx_location(client: Client) -> None:
    for url in ("/pipeline/cbv/", "/pipeline/fbv/"):
        plain = client.post(url, {"name": "x"})
        assert plain.status_code == 302
        response = client.post(url, {"name": "x"}, headers=HX)
        assert response.status_code == 200
        assert response["HX-Location"] == "/widgets/"
        assert "Location" not in response.headers


def test_plain_django_view_untouched(client: Client) -> None:
    response = client.post("/pipeline/plain/", {}, headers=HX)
    assert response.status_code == 200
    assert "HX-Request" not in response.headers.get("Vary", "")


def test_invalid_partial_post_is_422_with_partial_body(client: Client) -> None:
    for url in ("/pipeline/cbv/", "/pipeline/fbv/"):
        response = client.post(url, {}, headers=PARTIAL)
        assert response.status_code == 422
        body = response.content.decode()
        assert body.startswith('<form id="f">')
        assert "<html>" not in body


def test_redirect_conversion_keeps_other_headers() -> None:
    redirect = HttpResponse(status=302, headers={"Location": "/x/", "X-Custom": "1"})
    converted = redirect_to_location(redirect)
    assert converted.status_code == 200
    assert converted["HX-Location"] == "/x/"
    assert converted["X-Custom"] == "1"
    assert "Location" not in converted.headers


@pytest.mark.django_db
@pytest.mark.parametrize("headers", [{}, PARTIAL])
def test_use_it_409_is_always_a_standalone_document(headers: dict[str, str]) -> None:
    widget = Widget.objects.create(name="w", status="retired")
    user = User.objects.create_user("editor", password="pw")
    user.user_permissions.add(Permission.objects.get(codename="change_widget"))
    client = Client()
    client.force_login(user)
    response = client.post(f"/widget/{widget.pk}/renew/", headers=headers)
    assert response.status_code == 409
    body = response.content.decode()
    assert body.lower().startswith("<!doctype html")
    assert f'id="hm-widget-renew-{widget.pk}"' in body
    assert ("HX-Retarget" in response.headers) == bool(headers)
    assert ("HX-Reselect" in response.headers) == bool(headers)
