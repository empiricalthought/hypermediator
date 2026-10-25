from pathlib import Path
from typing import Any, cast

import pytest
from django.conf import settings
from django.http import HttpResponse
from django.test import override_settings

from hypermediator.extract import extract
from hypermediator.testing import violations
from tests.models import Widget
from tests.test_tags import make_request, only, render

pytestmark = pytest.mark.django_db

HERE = Path(__file__).resolve().parent
REASON = "Retired widgets cannot be renewed"
LINK = "{% hm_link 'widget-renew' w %}"
ACTION = "{% hm_action 'widget-renew' w %}"


def templates_with(directory: str) -> list[dict[str, Any]]:
    (engine,) = cast(list[dict[str, Any]], settings.TEMPLATES)
    return [{**engine, "DIRS": [HERE / directory, *engine["DIRS"]]}]


def conforms(html: str) -> list[str]:
    response = HttpResponse(html)
    response["Vary"] = "HX-Request, HX-Request-Type"
    return violations(response)


@pytest.fixture
def retired() -> Widget:
    return Widget.objects.create(name="r", status="retired")


def test_default_reason_markup(retired: Widget) -> None:
    html = render(LINK, make_request(can_change=True), w=retired)
    dom_id = f"hm-widget-renew-{retired.pk}"
    assert (
        f'aria-describedby="{dom_id}-reason">Renew</a>'
        f' (<small id="{dom_id}-reason" class="hm-reason">{REASON}</small>)'
    ) in html
    assert only(html, "widget-renew").reason == REASON


@override_settings(TEMPLATES=templates_with("override_templates"))
def test_overridden_reason_stays_conformant(retired: Widget) -> None:
    request = make_request(can_change=True)
    for source in (LINK, ACTION):
        html = render(source, request, w=retired)
        assert only(html, "widget-renew").reason == f"Unavailable: {REASON}"
        assert conforms(html) == []
        assert "(<small" not in html
        assert "hm-reason" not in html
        assert '<br><em id="' in html


@override_settings(TEMPLATES=templates_with("override_templates_noid"))
def test_override_without_id_is_a_violation(retired: Widget) -> None:
    html = render(LINK, make_request(can_change=True), w=retired)
    assert any(v.startswith("L2") for v in conforms(html))
    assert extract(html).by_name("widget-renew")[0].reason == ""
