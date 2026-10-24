import base64
import hashlib
from pathlib import Path

from django.template import engines

import hypermediator
from hypermediator.htmx import HTMX_SHA256, HTMX_VERSION

VENDORED = Path(hypermediator.__file__).parent / "static" / "hypermediator" / "htmx.min.js"


def test_vendored_file_matches_hash() -> None:
    digest = hashlib.sha256(VENDORED.read_bytes()).digest()
    assert "sha256-" + base64.b64encode(digest).decode() == HTMX_SHA256


def test_tag_renders_integrity() -> None:
    html = engines["django"].from_string("{% load hypermediator %}{% hm_htmx %}").render({})
    assert html == (
        f'<script src="/static/hypermediator/htmx.min.js" integrity="{HTMX_SHA256}" '
        'crossorigin="anonymous" defer></script>'
    )


def test_version_is_4() -> None:
    assert HTMX_VERSION.startswith("4.")
