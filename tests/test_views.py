import pytest
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, RequestFactory, override_settings
from django.urls import NoReverseMatch, reverse

from hypermediator.affordances import Placement
from hypermediator.endpoints import bind, endpoint_for
from hypermediator.extract import extract
from tests.models import Widget

pytestmark = pytest.mark.django_db


def make_user(username: str, *, can_change: bool = False) -> User:
    user = User.objects.create_user(username, password="pw")
    if can_change:
        user.user_permissions.add(Permission.objects.get(codename="change_widget"))
    return user


def request_for(user: User | None) -> object:
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
    hidden = bind(request_for(make_user("nobody")), "widget-renew", widget)  # type: ignore[arg-type]
    assert (hidden.state, hidden.reason) == ("hidden", None)

    retired = Widget.objects.create(name="r", status="retired")
    disabled = bind(request_for(make_user("a", can_change=True)), "widget-renew", retired)  # type: ignore[arg-type]
    assert (disabled.state, disabled.reason) == ("disabled", "Retired widgets cannot be renewed")

    enabled = bind(request_for(make_user("b", can_change=True)), "widget-renew", widget)  # type: ignore[arg-type]
    assert (enabled.state, enabled.reason) == ("enabled", None)
    assert enabled.url == reverse("widget-renew", args=[widget.pk])
    assert enabled.dom_id == f"hm-widget-renew-{widget.pk}"
    assert enabled.placement == Placement.ITEM


def test_bind_without_object_uses_page_placement_and_plain_id() -> None:
    bound = bind(request_for(make_user("c")), "widget-list")  # type: ignore[arg-type]
    assert bound.dom_id == "hm-widget-list"
    assert bound.url == reverse("widget-list")
    assert bound.placement == Placement.PAGE
    override = Placement(target="#x")
    assert bind(request_for(None), "widget-list", placement_override=override).placement is override  # type: ignore[arg-type]


def test_bind_fbv(widget: Widget) -> None:
    bound = bind(request_for(make_user("d", can_change=True)), "widget-renew-fbv", widget)  # type: ignore[arg-type]
    assert bound.state == "enabled"
    assert bind(request_for(make_user("e")), "widget-renew-fbv", widget).state == "hidden"  # type: ignore[arg-type]


def test_bind_undeclared_view_raises() -> None:
    with pytest.raises(LookupError):
        bind(request_for(None), "widget-plain")  # type: ignore[arg-type]


def test_bind_login_only_view_is_enabled_for_anonymous() -> None:
    bound = bind(request_for(None), "widget-list")  # type: ignore[arg-type]
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
