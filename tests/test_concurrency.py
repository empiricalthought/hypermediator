import re

import pytest
from django.test import Client

from hypermediator.concurrency import fingerprint
from tests.models import Widget

URL = "/widget/{}/edit-concurrent/"
HX = {"HX-Request": "true"}


def token(client: Client, widget: Widget) -> str:
    html = client.get(URL.format(widget.pk)).content.decode()
    match = re.search(r'name="_hm_fingerprint"[^>]*value="([0-9a-f]+)"', html)
    assert match, html
    return match.group(1)


@pytest.fixture
def widget(db: None) -> Widget:
    return Widget.objects.create(name="Original", status="a")


def test_fingerprint_stable_and_field_scoped(widget: Widget) -> None:
    first = fingerprint(widget, ["name"])
    assert first == fingerprint(Widget.objects.get(pk=widget.pk), ["name"])
    assert len(first) == 64
    Widget.objects.filter(pk=widget.pk).update(status="b")
    assert fingerprint(Widget.objects.get(pk=widget.pk), ["name"]) == first
    assert fingerprint(Widget.objects.get(pk=widget.pk), ["name", "status"]) != first


@pytest.mark.django_db
def test_stale_submit_is_409_keeps_user_values_and_shows_current(
    client: Client, widget: Widget
) -> None:
    stale = token(client, widget)
    Widget.objects.filter(pk=widget.pk).update(name="Theirs")
    response = client.post(URL.format(widget.pk), {"name": "Mine", "_hm_fingerprint": stale})
    assert response.status_code == 409
    body = response.content.decode()
    assert 'value="Mine"' in body
    assert (
        "This widget was changed by someone else since you opened the form. "
        "Review the current values and submit again." in body
    )
    assert 'id="id_name_current">Current value: Theirs</div>' in body
    assert stale not in body
    assert fingerprint(Widget.objects.get(pk=widget.pk), ["name"]) in body
    assert Widget.objects.get(pk=widget.pk).name == "Theirs"


@pytest.mark.django_db
def test_resubmit_with_fresh_fingerprint_succeeds(client: Client, widget: Widget) -> None:
    stale = token(client, widget)
    Widget.objects.filter(pk=widget.pk).update(name="Theirs")
    response = client.post(URL.format(widget.pk), {"name": "Mine", "_hm_fingerprint": stale})
    fresh = re.search(r'name="_hm_fingerprint"[^>]*value="([0-9a-f]+)"', response.content.decode())
    assert fresh
    again = client.post(URL.format(widget.pk), {"name": "Mine", "_hm_fingerprint": fresh.group(1)})
    assert again.status_code == 302
    assert Widget.objects.get(pk=widget.pk).name == "Mine"


@pytest.mark.django_db
@pytest.mark.parametrize("value", [None, "", "garbage", "0" * 64])
def test_missing_or_tampered_fingerprint_is_409(client: Client, widget: Widget, value: str) -> None:
    data = {"name": "Mine"}
    if value is not None:
        data["_hm_fingerprint"] = value
    assert client.post(URL.format(widget.pk), data).status_code == 409
    assert Widget.objects.get(pk=widget.pk).name == "Original"


@pytest.mark.django_db
def test_change_to_unexposed_field_does_not_conflict(client: Client, widget: Widget) -> None:
    current = token(client, widget)
    Widget.objects.filter(pk=widget.pk).update(status="b")
    response = client.post(URL.format(widget.pk), {"name": "Mine", "_hm_fingerprint": current})
    assert response.status_code == 302
    assert Widget.objects.get(pk=widget.pk).name == "Mine"


@pytest.mark.django_db
def test_no_etag_header(client: Client, widget: Widget) -> None:
    assert "ETag" not in client.get(URL.format(widget.pk))
    stale = token(client, widget)
    Widget.objects.filter(pk=widget.pk).update(name="Theirs")
    response = client.post(URL.format(widget.pk), {"name": "Mine", "_hm_fingerprint": stale})
    assert "ETag" not in response
    ignored = client.post(
        URL.format(widget.pk),
        {"name": "Mine", "_hm_fingerprint": stale},
        headers={"If-Match": '"x"'},
    )
    assert ignored.status_code == 409
