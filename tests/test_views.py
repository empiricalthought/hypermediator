import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpRequest
from django.template import engines
from django.test import Client, RequestFactory, override_settings
from django.urls import NoReverseMatch, reverse

from hypermediator.affordances import Placement
from hypermediator.endpoints import bind, endpoint_for
from hypermediator.extract import extract
from tests.models import Gadget, Widget

pytestmark = pytest.mark.django_db


def make_user(username: str, *, can_change: bool = False) -> User:
    user = User.objects.create_user(username, password="pw")
    if can_change:
        user.user_permissions.add(Permission.objects.get(codename="change_widget"))
    return user


def request_for(user: User | None) -> HttpRequest:
    request = RequestFactory().get("/")
    if user is None:
        from django.contrib.auth.models import AnonymousUser

        request.user = AnonymousUser()
    else:
        request.user = user
    return request


@pytest.fixture
def widget() -> Widget:
    return Widget.objects.create(name="w")


def test_cbv_post_without_permission_is_403(widget: Widget) -> None:
    client = Client()
    client.force_login(make_user("nobody"))
    assert client.post(reverse("widget-renew", args=[widget.pk])).status_code == 403


def test_cbv_post_unavailable_is_409_with_reason_in_body(widget: Widget) -> None:
    widget.status = "retired"
    widget.save()
    client = Client()
    client.force_login(make_user("editor", can_change=True))
    response = client.post(reverse("widget-renew", args=[widget.pk]))
    assert response.status_code == 409
    page = extract(response.content.decode())
    [control] = page.by_name("widget-renew")
    assert not control.enabled
    assert control.reason == "Retired widgets cannot be renewed"
    assert control.wrapper_id == f"hm-widget-renew-{widget.pk}"
    assert reverse("widget-detail", args=[widget.pk]) in response.content.decode()


def test_cbv_post_available_proceeds_to_the_view(widget: Widget) -> None:
    client = Client()
    client.force_login(make_user("editor", can_change=True))
    assert client.post(reverse("widget-renew", args=[widget.pk])).status_code == 200


def test_fbv_permission_403_and_unavailable_409(widget: Widget) -> None:
    url = reverse("widget-renew-fbv", args=[widget.pk])
    client = Client()
    client.force_login(make_user("nobody"))
    assert client.post(url).status_code == 403

    editor = Client()
    editor.force_login(make_user("editor", can_change=True))
    assert editor.post(url).status_code == 200
    widget.status = "retired"
    widget.save()
    response = editor.post(url)
    assert response.status_code == 409
    assert "Retired widgets cannot be renewed" in response.content.decode()


def test_fbv_attribute_survives_login_required() -> None:
    declaration = endpoint_for("widget-renew-fbv")
    assert declaration is not None
    assert declaration.declaration is not None
    assert declaration.declaration.permission == ("tests.change_widget",)
    assert declaration.methods == {"GET", "POST"}
    assert declaration.has_fields is False


def test_endpoint_for_cbv_and_undeclared() -> None:
    endpoint = endpoint_for("widget-renew")
    assert endpoint is not None
    assert endpoint.methods == {"GET", "POST"}
    assert endpoint.affordance.label == "Renew"
    login_only = endpoint_for("widget-list")
    assert login_only is not None
    assert login_only.methods == {"GET"}
    assert endpoint_for("widget-plain") is None


def test_cbv_allow_omits_post_when_view_has_no_post() -> None:
    client = Client()
    client.force_login(make_user("someone"))
    response = client.options(reverse("widget-list"))
    assert set(response["Allow"].split(", ")) == {"GET", "HEAD", "OPTIONS"}


def test_endpoint_cache_resets_on_root_urlconf_change() -> None:
    assert endpoint_for("widget-renew") is not None
    with (
        override_settings(ROOT_URLCONF="tests.urls_empty"),
        pytest.raises(NoReverseMatch, match="widget-renew"),
    ):
        endpoint_for("widget-renew")
    assert endpoint_for("widget-renew") is not None


def test_bind_hidden_disabled_enabled(widget: Widget) -> None:
    hidden = bind(request_for(make_user("nobody")), "widget-renew", widget)
    assert (hidden.state, hidden.reason) == ("hidden", None)

    retired = Widget.objects.create(name="r", status="retired")
    disabled = bind(request_for(make_user("a", can_change=True)), "widget-renew", retired)
    assert (disabled.state, disabled.reason) == ("disabled", "Retired widgets cannot be renewed")

    enabled = bind(request_for(make_user("b", can_change=True)), "widget-renew", widget)
    assert (enabled.state, enabled.reason) == ("enabled", None)
    assert enabled.url == reverse("widget-renew", args=[widget.pk])
    assert enabled.dom_id == f"hm-widget-renew-{widget.pk}"
    assert enabled.placement == Placement.ITEM


def test_bind_without_object_uses_page_placement_and_plain_id() -> None:
    bound = bind(request_for(make_user("c")), "widget-list")
    assert bound.dom_id == "hm-widget-list"
    assert bound.url == reverse("widget-list")
    assert bound.placement == Placement.PAGE
    override = Placement(target="#x")
    assert bind(request_for(None), "widget-list", placement_override=override).placement is override


def test_bind_fbv(widget: Widget) -> None:
    bound = bind(request_for(make_user("d", can_change=True)), "widget-renew-fbv", widget)
    assert bound.state == "enabled"
    assert bind(request_for(make_user("e")), "widget-renew-fbv", widget).state == "hidden"


def test_bind_undeclared_view_raises() -> None:
    with pytest.raises(LookupError):
        bind(request_for(None), "widget-plain")


def test_bind_login_only_view_is_enabled_for_anonymous() -> None:
    bound = bind(request_for(None), "widget-list")
    assert bound.state == "enabled"


def test_post_to_deleted_object_is_404(widget: Widget) -> None:
    client = Client()
    client.force_login(make_user("editor", can_change=True))
    url = reverse("widget-renew", args=[widget.pk])
    pk = widget.pk
    widget.delete()
    assert client.post(url).status_code == 404
    assert client.post(reverse("widget-renew-fbv", args=[pk])).status_code == 404


def test_unavailable_htmx_headers(widget: Widget) -> None:
    widget.status = "retired"
    widget.save()
    client = Client()
    client.force_login(make_user("editor", can_change=True))
    response = client.post(
        reverse("widget-renew", args=[widget.pk]), headers={"HX-Request": "true"}
    )
    assert response.status_code == 409
    dom_id = f"hm-widget-renew-{widget.pk}"
    assert response["HX-Retarget"] == f"#{dom_id}"
    assert response["HX-Reswap"] == "outerHTML"
    assert response["HX-Reselect"] == f"#{dom_id}"
    plain = client.post(reverse("widget-renew", args=[widget.pk]))
    assert "HX-Retarget" not in plain


def test_missing_url_name_is_a_configuration_error(widget: Widget) -> None:
    from hypermediator.views import _current_endpoint

    request = RequestFactory().post("/")
    with pytest.raises(ImproperlyConfigured):
        _current_endpoint(request)


def test_uuid_pk_route_binds_and_submits() -> None:
    gadget = Gadget.objects.create()
    bound = bind(request_for(None), "gadget-renew", gadget)
    assert bound.url == reverse("gadget-renew", args=[gadget.pk])
    assert bound.dom_id == f"hm-gadget-renew-{gadget.pk}"
    assert Client().post(bound.url).status_code == 200
    gadget.status = "retired"
    gadget.save()
    response = Client().post(bound.url)
    assert response.status_code == 409
    assert "Retired" in response.content.decode()


def test_namespaced_name_resolves_and_submits(widget: Widget) -> None:
    assert endpoint_for("ns:renew") is not None
    client = Client()
    client.force_login(make_user("editor", can_change=True))
    url = reverse("ns:renew", args=[widget.pk])
    assert client.post(url).status_code == 200
    widget.status = "retired"
    widget.save()
    response = client.post(url)
    assert response.status_code == 409
    [control] = extract(response.content.decode()).by_name("ns:renew")
    assert not control.enabled


def test_create_view_unavailable_judged_on_none() -> None:
    client = Client()
    assert client.post(reverse("widget-create"), {"name": "new"}).status_code == 302
    assert Widget.objects.filter(name="new").exists()
    Widget.objects.create(name="full", status="full")
    response = client.post(reverse("widget-create"), {"name": "later"})
    assert response.status_code == 409
    assert "Creation is closed" in response.content.decode()
    assert not Widget.objects.filter(name="later").exists()


@override_settings(ROOT_URLCONF="tests.urls_methods")
def test_delete_to_unavailable_is_409_and_row_survives() -> None:
    retired = Widget.objects.create(name="r", status="retired")
    response = Client().delete(reverse("widget-delete", args=[retired.pk]))
    assert response.status_code == 409
    assert Widget.objects.filter(pk=retired.pk).exists()
    ok = Widget.objects.create(name="ok")
    assert Client().delete(reverse("widget-delete", args=[ok.pk])).status_code == 302
    assert not Widget.objects.filter(pk=ok.pk).exists()


@override_settings(ROOT_URLCONF="tests.urls_methods")
def test_put_to_unavailable_update_is_409() -> None:
    retired = Widget.objects.create(name="r", status="retired")
    response = Client().put(
        reverse("widget-update", args=[retired.pk]),
        "name=changed",
        content_type="application/x-www-form-urlencoded",
    )
    assert response.status_code == 409
    retired.refresh_from_db()
    assert retired.name == "r"


def test_post_to_get_only_view_is_405_like_django(widget: Widget) -> None:
    assert Client().post(reverse("widget-view", args=[widget.pk])).status_code == 405


def test_options_allow_equals_plain_django(widget: Widget) -> None:
    ours = Client().options(reverse("widget-view", args=[widget.pk]))
    plain = Client().options(reverse("widget-plain-view", args=[widget.pk]))
    assert set(ours["Allow"].split(", ")) == set(plain["Allow"].split(", "))


HX = {"HX-Request": "true"}


def _vary(response: object) -> set[str]:
    header: str = getattr(response, "headers", {}).get("Vary", "")
    return {token.strip() for token in header.split(",")}


def test_fbv_409_carries_vary(widget: Widget) -> None:
    widget.status = "retired"
    widget.save()
    client = Client()
    client.force_login(make_user("editor", can_change=True))
    response = client.post(reverse("widget-renew-fbv", args=[widget.pk]))
    assert response.status_code == 409
    assert {"HX-Request", "HX-Request-Type"} <= _vary(response)


def test_fbv_use_it_guards_every_unsafe_method() -> None:
    gadget = Gadget.objects.create(status="retired")
    url = reverse("gadget-renew", args=[gadget.pk])
    for method in ("delete", "put", "patch"):
        assert getattr(Client(), method)(url).status_code == 409, method
    assert Client().get(url).status_code == 200


def test_namespaced_dom_id_is_a_valid_css_id(widget: Widget) -> None:
    bound = bind(request_for(make_user("ns", can_change=True)), "ns:renew", widget)
    assert bound.dom_id == f"hm-ns-renew-{widget.pk}"
    widget.status = "retired"
    widget.save()
    client = Client()
    client.force_login(make_user("editor", can_change=True))
    response = client.post(reverse("ns:renew", args=[widget.pk]), headers=HX)
    assert response.status_code == 409
    assert response["HX-Retarget"] == f"#hm-ns-renew-{widget.pk}"
    [control] = extract(response.content.decode()).by_name("ns:renew")
    assert control.wrapper_id == f"hm-ns-renew-{widget.pk}"


def test_slug_routed_cbv_binds_renders_and_refuses() -> None:
    from django.template import engines

    widget = Widget.objects.create(name="sprocket")
    url = reverse("widget-renew-slug", kwargs={"slug": "sprocket"})
    request = request_for(None)
    bound = bind(request, "widget-renew-slug", widget)
    assert bound.url == url
    html = (
        engines["django"]
        .from_string("{% load hypermediator %}{% hm_link 'widget-renew-slug' w %}")
        .render({"request": request, "w": widget})
    )
    [link] = extract(html).by_name("widget-renew-slug")
    assert link.href == url

    widget.status = "retired"
    widget.save()
    response = Client().post(url)
    assert response.status_code == 409
    [control] = extract(response.content.decode()).by_name("widget-renew-slug")
    assert control.reason == "Retired widgets cannot be renewed"
    assert control.wrapper_id == f"hm-widget-renew-slug-{widget.pk}"


def test_fbv_permission_anonymous_redirects_to_login_like_django() -> None:
    url = reverse("widget-guarded-fbv")
    response = Client().get(f"{url}?x=1")
    assert response.status_code == 302
    assert response["Location"] == "/accounts/login/?next=/widgets/guarded-fn/%3Fx%3D1"
    client = Client()
    client.force_login(make_user("nobody"))
    assert client.get(url).status_code == 403
    editor = Client()
    editor.force_login(make_user("editor", can_change=True))
    assert editor.get(url).status_code == 200


def test_htmx_post_auth_mixin_redirect_is_not_converted() -> None:
    url = reverse("widget-login-post")
    response = Client().post(url, headers=HX)
    assert response.status_code == 302
    assert response["Location"] == f"/accounts/login/?next={url}"
    assert "HX-Location" not in response.headers
    client = Client()
    client.force_login(make_user("member"))
    converted = client.post(url, headers=HX)
    assert converted.status_code == 200
    assert converted["HX-Location"] == "/widgets/"


def test_fbv_url_kwargs_maps_the_object_to_its_route() -> None:
    widget = Widget.objects.create(name="sprocket")
    bound = bind(request_for(None), "widget-rename-fbv", widget)
    assert bound.url == reverse("widget-rename-fbv", kwargs={"name": "sprocket"})


@override_settings(ROOT_URLCONF="tests.urls_include")
def test_include_prefix_pk_binds_and_renders(widget: Widget) -> None:
    endpoint_for.cache_clear()
    try:
        bound = bind(request_for(make_user("editor", can_change=True)), "inc-renew", widget)
        assert bound.url == f"/lib/{widget.pk}/renew/"
        user = make_user("editor2", can_change=True)
        html = (
            engines["django"]
            .from_string("{% load hypermediator %}{% hm_link 'inc-renew' w %}")
            .render({"request": request_for(user), "w": widget})
        )
        [control] = extract(html).by_name("inc-renew")
        assert control.wrapper_id == f"hm-inc-renew-{widget.pk}"
    finally:
        endpoint_for.cache_clear()


@override_settings(ROOT_URLCONF="tests.urls_include")
def test_include_prefix_pk_409_renders() -> None:
    endpoint_for.cache_clear()
    try:
        retired = Widget.objects.create(name="r", status="retired")
        client = Client()
        client.force_login(make_user("editor", can_change=True))
        response = client.post(f"/lib/{retired.pk}/renew/")
        assert response.status_code == 409
        [control] = extract(response.content.decode()).by_name("inc-renew")
        assert not control.enabled
        assert control.wrapper_id == f"hm-inc-renew-{retired.pk}"
    finally:
        endpoint_for.cache_clear()


@override_settings(ROOT_URLCONF="tests.urls_include")
def test_route_without_pk_or_slug_kwarg_is_improperly_configured(widget: Widget) -> None:
    endpoint_for.cache_clear()
    try:
        with pytest.raises(ImproperlyConfigured, match=r"odd-renew.*ident"):
            bind(request_for(make_user("editor", can_change=True)), "odd-renew", widget)
    finally:
        endpoint_for.cache_clear()
