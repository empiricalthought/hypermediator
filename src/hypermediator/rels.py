"""Link-relation vocabulary: which rel tokens HTML permits on which element."""

from collections.abc import Iterable
from typing import Literal

_COMMON = frozenset(
    (
        "external",
        "help",
        "license",
        "next",
        "nofollow",
        "noopener",
        "noreferrer",
        "opener",
        "prev",
        "search",
    )
)
_A_RELS = _COMMON | {"alternate", "author", "bookmark", "privacy-policy", "tag", "terms-of-service"}
_FORM_RELS = _COMMON


def html_rels(tokens: Iterable[str], element: Literal["a", "form"]) -> tuple[str, ...]:
    """Keep only the tokens HTML allows in the rel attribute of ``element``."""
    allowed = _A_RELS if element == "a" else _FORM_RELS
    return tuple(token for token in tokens if token in allowed)
