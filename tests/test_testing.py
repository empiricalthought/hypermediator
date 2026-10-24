import pytest
from django.http import HttpResponse
from django.test import Client

from hypermediator.testing import (
    assert_allow_matches,
    assert_conforms,
    assert_get_does_not_change_state,
    assert_same_affordances,
    violations,
)
from tests.models import Widget

VARY = "HX-Request, HX-Request-Type"


def _meta(name: str, control: str) -> str:
    return (
        '<span hidden itemscope itemtype="urn:hypermediator:Affordance">'
        f'<meta itemprop="name" content="{name}">'
        f'<meta itemprop="control" content="{control}"></span>'
    )


def _link(name: str, label: str = "Go", attrs: str = 'href="/x/"') -> str:
    return (
        f'<span class="hm-control" id="hm-{name}"><a id="hm-{name}-c" {attrs}>{label}</a>'
        + _meta(name, f"hm-{name}-c")
        + "</span>"
    )


def _disabled(name: str, reason: str = "Not now") -> str:
    return (
        f'<span class="hm-control" id="hm-{name}">'
        f'<a id="hm-{name}-c" role="link" aria-disabled="true" '
        f'aria-describedby="hm-{name}-reason">Go</a>'
        f'<span id="hm-{name}-reason">{reason}</span>' + _meta(name, f"hm-{name}-c") + "</span>"
    )


def _response(html: str, vary: str | None = VARY) -> HttpResponse:
    response = HttpResponse(html)
    if vary is not None:
        response["Vary"] = vary
    return response


def _found(html: str, layer: str, vary: str | None = VARY) -> list[str]:
    return [v for v in violations(_response(html, vary)) if v.startswith(layer)]


def test_conforming_page_has_no_violations() -> None:
    html = _link("a") + _disabled("b")
    assert violations(_response(html)) == []
    assert assert_conforms(_response(html)).by_name("a")


def test_assert_conforms_lists_violations() -> None:
    with pytest.raises(AssertionError, match="L2: control 'x' has no accessible name"):
        assert_conforms(_response('<a id="x" href="/x/"></a>'))


def test_l1_form_method_must_be_get_or_post() -> None:
    bad = '<form id="f" action="/x/" method="put"><button>Go</button></form>'
    good = '<form id="f" action="/x/" method="get"><button>Go</button></form>'
    assert any("method" in v for v in _found(bad, "L1"))
    assert _found(good, "L1") == []


def test_l1_enabled_control_needs_href_or_action() -> None:
    assert any("href" in v for v in _found('<a id="x" href="">Go</a>', "L1"))
    assert _found('<a id="x" href="/x/">Go</a>', "L1") == []


def test_l1_plain_anchor_target_is_not_a_control() -> None:
    assert violations(_response('<a id="top"></a><p>text</p>')) == []


def test_l2_control_needs_accessible_name() -> None:
    assert any("accessible name" in v for v in _found(_link("a", label=""), "L2"))


def test_l2_field_needs_accessible_name() -> None:
    bad = '<form id="f" action="/x/" method="post"><input name="q"><button>Go</button></form>'
    good = (
        '<form id="f" action="/x/" method="post"><label for="q">Q</label>'
        '<input id="q" name="q"><button>Go</button></form>'
    )
    assert any("field 'q'" in v for v in _found(bad, "L2"))
    assert _found(good, "L2") == []


def test_l2_disabled_control_needs_reason() -> None:
    assert any("reason" in v for v in _found(_disabled("b", reason=""), "L2"))
    assert _found(_disabled("b"), "L2") == []


def test_l2_duplicate_ids() -> None:
    html = _link("a") + '<p id="hm-a">again</p>'
    assert any("duplicate id 'hm-a'" in v for v in _found(html, "L2"))


def test_l3_rel_must_be_valid_for_element() -> None:
    bad = '<a id="x" href="/x/" rel="edit">Go</a>'
    good = '<a id="x" href="/x/" rel="next">Go</a>'
    assert any("rel 'edit'" in v for v in _found(bad, "L3"))
    assert _found(good, "L3") == []


def test_l3_microdata_needs_name_and_resolvable_control() -> None:
    nameless = _link("a").replace('<meta itemprop="name" content="a">', "")
    assert any("name" in v for v in _found(nameless, "L3"))
    orphan = '<span class="hm-control" id="w"><a id="w-c" href="/x/">Go</a></span>'
    assert any("microdata" in v for v in _found(orphan, "L3"))
    assert _found(_link("a"), "L3") == []


def test_l4_hx_only_on_native_controls_with_href_or_action() -> None:
    assert any("hx-get" in v for v in _found('<a id="x" hx-get="/x/">Go</a>', "L4"))
    assert any("hx-" in v for v in _found('<div hx-get="/x/"><p>no control</p></div>', "L4"))
    assert _found('<a id="x" href="/x/" hx-get="/x/">Go</a>', "L4") == []
    assert _found('<div hx-get="/x/"><a href="/x/">Go</a></div>', "L4") == []


def test_l4_vary_includes_both_htmx_headers_with_managed_controls() -> None:
    html = _link("a")
    assert any("HX-Request-Type" in v for v in _found(html, "L4", vary="HX-Request"))
    assert any("Vary" in v for v in _found(html, "L4", vary=None))
    assert _found(html, "L4", vary="Cookie, hx-request, HX-Request-Type") == []
    assert _found('<a href="/x/">Go</a>', "L4", vary=None) == []


def test_same_affordances_ignores_content_outside_fragment() -> None:
    full = _response(_link("a") + _disabled("b") + _link("c"))
    fragment = _response(_link("a") + _disabled("b"))
    assert_same_affordances(full, fragment)


def test_same_affordances_detects_state_and_missing_controls() -> None:
    full = _response(_link("a") + _link("b"))
    with pytest.raises(AssertionError):
        assert_same_affordances(full, _response(_link("a") + _disabled("b")))
    with pytest.raises(AssertionError):
        assert_same_affordances(_response(_link("a")), _response(_link("a") + _link("b")))


@pytest.mark.django_db
def test_allow_matches(client: Client) -> None:
    assert_allow_matches(client, "/widgets/next/", "widget-next")
    with pytest.raises(AssertionError, match="PUT"):  # FormView also allows PUT (R5)
        assert_allow_matches(client, "/pipeline/cbv/", "pipeline-cbv")
    with pytest.raises(AssertionError, match="Allow"):
        assert_allow_matches(client, "/widget/1/renew/", "widget-renew")
    with pytest.raises(AssertionError, match="declares no affordance"):
        assert_allow_matches(client, "/plain/", "widget-plain")


@pytest.mark.django_db
def test_get_does_not_change_state(client: Client) -> None:
    Widget.objects.create(name="w")
    assert_get_does_not_change_state(client, "/widget/1/")
    with pytest.raises(AssertionError, match=r"tests\.Widget"):
        assert_get_does_not_change_state(client, "/mutating/")
