"""Paginated lists: each page conforms and links its neighbours with rel="next" and rel="prev"."""

import pytest
from django.test import Client
from django.urls import reverse

from catalog.models import Author, Book
from hypermediator.extract import Page
from hypermediator.testing import assert_conforms

pytestmark = pytest.mark.django_db

PER_PAGE = 10


@pytest.fixture
def eleven_of_each() -> None:
    for n in range(PER_PAGE + 1):
        author = Author.objects.create(first_name="Author", last_name=f"Number {n:02}")
        Book.objects.create(title=f"Book {n:02}", author=author, summary="A book.", isbn=f"{n:013}")


def _rel_hrefs(page: Page, rel: str) -> list[str | None]:
    return [c.href for c in page.controls if rel in c.element_rel]


@pytest.mark.usefixtures("eleven_of_each")
@pytest.mark.parametrize("url_name", ["books", "authors"])
def test_pages_conform_and_link_next_and_prev(client: Client, url_name: str) -> None:
    url = reverse(url_name)
    first = assert_conforms(client.get(url))
    assert _rel_hrefs(first, "next") == ["?page=2"]
    assert _rel_hrefs(first, "prev") == []

    second = assert_conforms(client.get(f"{url}?page=2"))
    assert _rel_hrefs(second, "prev") == ["?page=1"]
    assert _rel_hrefs(second, "next") == []
