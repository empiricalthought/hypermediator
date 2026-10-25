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


def test_rel_must_be_a_sequence_of_tokens_not_a_string() -> None:
    from hypermediator.views import affordance

    with pytest.raises(TypeError):
        Affordance(label="Edit", rel="edit")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        affordance(label="Edit", rel="edit")


def test_iana_token_must_match_whole_string() -> None:
    with pytest.raises(ValueError):
        Affordance(label="Edit", rel=("edit\n",))


@pytest.mark.parametrize(
    "token", ['https://x.example/r"', "https://x.example/a\\b", "https://x.example/a b", "urn:a\tb"]
)
def test_uri_rel_rejects_quote_backslash_and_whitespace(token: str) -> None:
    with pytest.raises(ValueError):
        Affordance(label="Go", rel=(token,))
