import dataclasses

import pytest

from hypermediator.affordances import Affordance, Placement
from hypermediator.rels import html_rels


def test_rel_tokens_validated() -> None:
    Affordance(label="Renew", rel=("edit", "https://locallibrary.example/rels/renew"))
    with pytest.raises(ValueError):
        Affordance(label="Renew", rel=("Not A Rel",))
    with pytest.raises(ValueError):
        Affordance(label="", rel=())


def test_rel_rejects_scheme_without_remainder() -> None:
    with pytest.raises(ValueError):
        Affordance(label="Renew", rel=("urn:",))


def test_html_rels_filters_per_element() -> None:
    assert html_rels(["next", "edit", "https://x.example/r"], "a") == ("next",)
    assert html_rels(["tag", "search"], "form") == ("search",)


def test_placement_sentinels() -> None:
    expected_item = Placement(target="closest [data-hm-item]", select="item")
    expected_page = Placement(target="body", swap="innerHTML", select="body", push_url=True)
    assert expected_item == Placement.ITEM
    assert expected_page == Placement.PAGE
    assert Placement.ITEM.swap == "outerHTML"
    with pytest.raises(dataclasses.FrozenInstanceError):
        Placement.ITEM.target = "x"  # type: ignore[misc]


def test_affordance_defaults_and_frozen() -> None:
    affordance = Affordance(label="Go")
    assert affordance.rel == ()
    assert affordance.placement is None
    assert affordance.trigger is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        affordance.label = "x"  # type: ignore[misc]
