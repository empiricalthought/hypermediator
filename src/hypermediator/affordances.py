"""The affordance model: what a control is called, means, and where its response lands."""

import re
from dataclasses import dataclass
from typing import ClassVar
from urllib.parse import urlsplit

_IANA_TOKEN = re.compile(r"[a-z][a-z0-9.\-]*")
_URI_FORBIDDEN = re.compile(r'["\\\s]')


@dataclass(frozen=True)
class Placement:
    """Where htmx puts a response. ``select="item"`` means the bound object's item selector."""

    target: str
    swap: str = "outerHTML"
    select: str | None = None
    push_url: bool = False

    ITEM: ClassVar[Placement]
    PAGE: ClassVar[Placement]


Placement.ITEM = Placement(target="closest [data-hm-item]", select="item")
Placement.PAGE = Placement(target="body", swap="innerHTML", select="body", push_url=True)


def _is_absolute_uri(token: str) -> bool:
    """An absolute URI that can sit in a quoted ``Link`` rel and an attribute unchanged."""
    if _URI_FORBIDDEN.search(token):
        return False
    _, separator, rest = token.partition(":")
    return bool(urlsplit(token).scheme) and bool(separator) and bool(rest)


@dataclass(frozen=True)
class Affordance:
    """A named, labelled control. A ``placement`` of None resolves to ITEM when bound to an
    object and to PAGE otherwise."""

    label: str
    rel: tuple[str, ...] = ()
    placement: Placement | None = None
    trigger: str | None = None

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("Affordance label must not be empty")
        if isinstance(self.rel, str):
            raise TypeError(f"Affordance rel must be a sequence of tokens, not {self.rel!r}")
        for token in self.rel:
            if not (_IANA_TOKEN.fullmatch(token) or _is_absolute_uri(token)):
                raise ValueError(f"Invalid rel token: {token!r}")
