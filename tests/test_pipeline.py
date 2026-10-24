from django.test import Client

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
    assert "Vary" not in response.headers or "HX-Request" not in response["Vary"]
