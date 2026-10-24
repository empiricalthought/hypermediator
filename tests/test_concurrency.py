import contextlib
import datetime
import re
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from unittest import mock

import pytest
from django.db import models, transaction
from django.db.models import Prefetch
from django.db.models.signals import pre_save
from django.test import Client
from django.utils import timezone

from hypermediator.concurrency import fingerprint
from tests.models import Thing, Widget

URL = "/widget/{}/edit-concurrent/"
HX = {"HX-Request": "true"}


def token(client: Client, widget: Widget | Thing, url: str = URL) -> str:
    html = client.get(url.format(widget.pk)).content.decode()
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


THING_FIELDS = ["when", "stamp", "price", "owner", "tags", "note"]
THING_URL = "/thing/{}/edit/"


@pytest.fixture
def thing(widget: Widget) -> Thing:
    thing = Thing.objects.create(
        when=datetime.date(2026, 1, 2),
        stamp=datetime.datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=datetime.UTC),
        price=Decimal("12.50"),
        owner=widget,
    )
    other = Widget.objects.create(name="Other")
    thing.tags.set([widget, other])
    return thing


def thing_post(thing: Thing, stale: str, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "when": "2026-01-02",
        "stamp": timezone.localtime(thing.stamp).strftime("%Y-%m-%d %H:%M:%S.%f"),
        "price": "12.50",
        "owner": thing.owner_id,
        "tags": [w.pk for w in thing.tags.all()],
        "note": "",
        "_hm_fingerprint": stale,
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_fingerprint_ignores_related_names_and_query_order(thing: Thing) -> None:
    before = fingerprint(thing, THING_FIELDS)
    assert thing.owner is not None
    renamed = thing.owner
    renamed.name = "Renamed"
    renamed.save()
    reordered = Thing.objects.prefetch_related(
        Prefetch("tags", Widget.objects.order_by("-pk"))
    ).get(pk=thing.pk)
    assert fingerprint(Thing.objects.get(pk=thing.pk), THING_FIELDS) == before
    assert fingerprint(reordered, THING_FIELDS) == before
    thing.tags.remove(thing.tags.all()[0])
    assert fingerprint(Thing.objects.get(pk=thing.pk), THING_FIELDS) != before


@pytest.mark.django_db
def test_rendered_fingerprint_equals_fresh_for_risk_types(client: Client, thing: Thing) -> None:
    html = client.get(THING_URL.format(thing.pk)).content.decode()
    match = re.search(r'name="_hm_fingerprint"[^>]*value="([0-9a-f]+)"', html)
    assert match
    assert match.group(1) == fingerprint(Thing.objects.get(pk=thing.pk), THING_FIELDS)


@pytest.mark.django_db
def test_unchanged_round_trip_of_risk_types_is_not_409(client: Client, thing: Thing) -> None:
    html = client.get(THING_URL.format(thing.pk)).content.decode()
    match = re.search(r'name="_hm_fingerprint"[^>]*value="([0-9a-f]+)"', html)
    assert match
    response = client.post(THING_URL.format(thing.pk), thing_post(thing, match.group(1)))
    assert response.status_code == 302


@pytest.mark.django_db
def test_current_value_for_m2m_only_when_changed_and_readable(client: Client, thing: Thing) -> None:
    stale = token(client, thing, THING_URL)
    Thing.objects.filter(pk=thing.pk).update(note="Theirs")
    body = client.post(THING_URL.format(thing.pk), thing_post(thing, stale)).content.decode()
    assert "id_note_current" in body
    assert "id_tags_current" not in body
    assert "id_owner_current" not in body
    assert "id_price_current" not in body
    assert "id_when_current" not in body
    assert "id_stamp_current" not in body
    keep = Widget.objects.get(name="Other")
    thing.tags.set([keep])
    stale = token(client, thing, THING_URL)
    thing.tags.set([Widget.objects.get(name="Original")])
    body = client.post(
        THING_URL.format(thing.pk), thing_post(thing, stale, tags=[keep.pk])
    ).content.decode()
    assert 'id="id_tags_current">Current value: Original</div>' in body
    assert "QuerySet" not in body


@pytest.mark.django_db
def test_exclude_on_form_is_honoured(client: Client, widget: Widget) -> None:
    url = "/widget/{}/edit-all/"
    current = token(client, widget, url)
    Widget.objects.filter(pk=widget.pk).update(status="b")
    response = client.post(url.format(widget.pk), {"name": "Mine", "_hm_fingerprint": current})
    assert response.status_code == 302


@pytest.mark.django_db
def test_stale_and_invalid_reports_only_the_conflict(client: Client, widget: Widget) -> None:
    stale = token(client, widget)
    Widget.objects.filter(pk=widget.pk).update(name="Theirs")
    response = client.post(URL.format(widget.pk), {"name": "", "_hm_fingerprint": stale})
    assert response.status_code == 409
    body = response.content.decode()
    assert "changed by someone else" in body
    assert "This field is required" not in body


@pytest.mark.django_db
def test_use_it_reason_wins_over_stale_fingerprint(client: Client, widget: Widget) -> None:
    stale = token(client, widget)
    Widget.objects.filter(pk=widget.pk).update(name="Theirs", status="retired")
    response = client.post(URL.format(widget.pk), {"name": "Mine", "_hm_fingerprint": stale})
    assert response.status_code == 409
    body = response.content.decode()
    assert "Retired widgets cannot be renewed" in body
    assert "changed by someone else" not in body


@pytest.mark.django_db
def test_check_and_save_share_one_locked_atomic_block(client: Client, widget: Widget) -> None:
    current = token(client, widget)
    events: list[tuple[str, int]] = []
    depth = 0
    real_atomic = transaction.atomic
    real_lock = models.QuerySet.select_for_update

    @contextlib.contextmanager
    def counting_atomic(*args: Any, **kwargs: Any) -> Iterator[None]:
        nonlocal depth
        with real_atomic(*args, **kwargs):
            depth += 1
            events.append(("enter", depth))
            try:
                yield
            finally:
                depth -= 1

    def locking(self: Any, *args: Any, **kwargs: Any) -> Any:
        events.append(("lock", depth))
        return real_lock(self, *args, **kwargs)

    def saving(**_: Any) -> None:
        events.append(("save", depth))

    pre_save.connect(saving, sender=Widget)
    try:
        with (
            mock.patch("hypermediator.concurrency.transaction.atomic", counting_atomic),
            mock.patch.object(models.QuerySet, "select_for_update", locking),
        ):
            response = client.post(
                URL.format(widget.pk), {"name": "Mine", "_hm_fingerprint": current}
            )
    finally:
        pre_save.disconnect(saving, sender=Widget)
    assert response.status_code == 302
    assert events == [("enter", 1), ("lock", 1), ("save", 1)]


@pytest.mark.django_db
def test_htmx_submit_of_default_placement_form_navigates(client: Client, widget: Widget) -> None:
    # placement=None on a pk URL: the full form targets itself, so a success redirect must not
    # be followed into the swap. Only an item refresh (HX-Hm-Item) follows it.
    url = URL.format(widget.pk)
    response = client.post(
        url, {"name": "Mine", "_hm_fingerprint": token(client, widget)}, headers=HX
    )
    assert response.status_code == 200
    assert response["HX-Location"] == "/widgets/"
    assert "Location" not in response.headers
    item = HX | {"HX-Hm-Item": f"tests.widget:{widget.pk}"}
    followed = client.post(
        url, {"name": "Again", "_hm_fingerprint": token(client, widget)}, headers=item
    )
    assert followed.status_code == 302
    assert followed["Location"] == "/widgets/"
    assert "HX-Location" not in followed.headers
