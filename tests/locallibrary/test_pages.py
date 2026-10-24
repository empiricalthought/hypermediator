"""Every LocalLibrary page against the four layers, per role."""

from collections.abc import Iterator
from html.parser import HTMLParser

import pytest
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import reverse

from catalog.models import Author, Book, BookInstance
from hypermediator.testing import (
    assert_allow_matches,
    assert_conforms,
    assert_get_does_not_change_state,
)

Pages = dict[str, tuple[str, dict[str, object]]]


@pytest.fixture
def pages(author: Author, book: Book, on_loan_copy: BookInstance) -> Pages:
    """Every GET page of the example, keyed by URL name."""
    author_kwargs: dict[str, object] = {"pk": author.pk}
    book_kwargs: dict[str, object] = {"pk": book.pk}
    return {
        "index": ("index", {}),
        "books": ("books", {}),
        "book-detail": ("book-detail", book_kwargs),
        "authors": ("authors", {}),
        "author-detail": ("author-detail", author_kwargs),
        "my-borrowed": ("my-borrowed", {}),
        "all-borrowed": ("all-borrowed", {}),
        "renew-book-librarian": ("renew-book-librarian", {"pk": on_loan_copy.pk}),
        "author-create": ("author-create", {}),
        "author-update": ("author-update", author_kwargs),
        "author-delete": ("author-delete", author_kwargs),
        "book-create": ("book-create", {}),
        "book-update": ("book-update", book_kwargs),
        "book-delete": ("book-delete", book_kwargs),
    }


PUBLIC = ("index", "books", "book-detail", "authors", "author-detail")
LOGIN_ONLY = ("my-borrowed",)
STAFF_ONLY = (
    "all-borrowed",
    "renew-book-librarian",
    "author-create",
    "author-update",
    "author-delete",
    "book-create",
    "book-update",
    "book-delete",
)
ALL_PAGES = PUBLIC + LOGIN_ONLY + STAFF_ONLY


def _expected_status(role: str, name: str) -> int:
    if name in PUBLIC:
        return 200
    if role == "anonymous":
        return 302
    if name in LOGIN_ONLY or role == "librarian":
        return 200
    return 403


def _login(client: Client, role: str, librarian: User, member: User) -> None:
    if role == "librarian":
        client.force_login(librarian)
    elif role == "member":
        client.force_login(member)


@pytest.mark.parametrize("name", ALL_PAGES)
@pytest.mark.parametrize("role", ["anonymous", "member", "librarian"])
def test_all_pages_conform_per_role(
    client: Client, librarian: User, member: User, pages: Pages, role: str, name: str
) -> None:
    _login(client, role, librarian, member)
    url_name, kwargs = pages[name]
    response = client.get(reverse(url_name, kwargs=kwargs))
    assert response.status_code == _expected_status(role, name)
    if response.status_code == 200:
        assert_conforms(response)


@pytest.mark.parametrize(
    "name",
    [
        "renew-book-librarian",
        "author-create",
        "author-update",
        "author-delete",
        "book-create",
        "book-update",
        "book-delete",
    ],
)
def test_allow_matches_on_affordance_urls(
    client: Client, librarian: User, pages: Pages, name: str
) -> None:
    client.force_login(librarian)
    url_name, kwargs = pages[name]
    assert_allow_matches(client, reverse(url_name, kwargs=kwargs), url_name)


@pytest.mark.parametrize("name", ALL_PAGES)
def test_gets_do_not_change_state(client: Client, librarian: User, pages: Pages, name: str) -> None:
    client.force_login(librarian)
    url_name, kwargs = pages[name]
    # MDN's index counts visits in the session on every GET; that write is the app's, not
    # hypermediator's, so the session table is the one state excluded from the check.
    assert_get_does_not_change_state(client, reverse(url_name, kwargs=kwargs), exclude=(Session,))


def test_link_header_on_book_detail(
    client: Client, librarian: User, book: Book, on_loan_copy: BookInstance
) -> None:
    client.force_login(librarian)
    link = client.get(book.get_absolute_url())["Link"]
    assert f'<{reverse("book-update", kwargs={"pk": book.pk})}>; rel="edit"' in link
    renew = reverse("renew-book-librarian", kwargs={"pk": on_loan_copy.pk})
    assert f'<{renew}>; rel="https://locallibrary.example/rels/renew"' in link
    # Disabled affordances are not advertised.
    assert reverse("book-delete", kwargs={"pk": book.pk}) not in link


def test_link_header_on_author_detail(client: Client, librarian: User, author: Author) -> None:
    client.force_login(librarian)
    link = client.get(author.get_absolute_url())["Link"]
    assert f'<{reverse("author-update", kwargs={"pk": author.pk})}>; rel="edit"' in link


def test_vary_on_hypermediator_pages(client: Client, librarian: User, pages: Pages) -> None:
    client.force_login(librarian)
    for name in ALL_PAGES:
        url_name, kwargs = pages[name]
        vary = client.get(reverse(url_name, kwargs=kwargs)).headers.get("Vary", "")
        tokens = {t.strip().lower() for t in vary.split(",")}
        assert {"hx-request", "hx-request-type"} <= tokens, name


class _Microdata(HTMLParser):
    """Collects, per itemscope, the itemprop names that belong directly to it."""

    _VOID = frozenset({"meta", "link", "br", "hr", "img", "input"})

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, int | None]] = []  # (tag, scope index it opened)
        self.scopes: list[tuple[str, list[str]]] = []  # (itemtype, own itemprops)
        self.current: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        prop = attributes.get("itemprop")
        if prop and self.current:
            self.scopes[self.current[-1]][1].append(prop)
        opened = None
        if "itemscope" in attributes:
            self.scopes.append((attributes.get("itemtype") or "", []))
            opened = len(self.scopes) - 1
            if tag in self._VOID:
                return
            self.current.append(opened)
        if tag not in self._VOID:
            self.stack.append((tag, opened))

    def handle_endtag(self, tag: str) -> None:
        while self.stack:
            open_tag, opened = self.stack.pop()
            if opened is not None:
                self.current.pop()
            if open_tag == tag:
                break

    def props_of(self, itemtype: str) -> Iterator[list[str]]:
        return (props for kind, props in self.scopes if kind == itemtype)


def test_schema_org_book_props_not_captured(client: Client, librarian: User, book: Book) -> None:
    client.force_login(librarian)
    walker = _Microdata()
    walker.feed(client.get(book.get_absolute_url()).content.decode())
    [props] = walker.props_of("https://schema.org/Book")
    # Only the template's own declaration; the affordances' name, control and rel metas
    # belong to their own urn:hypermediator:Affordance items.
    assert props == ["name"]
    affordances = list(walker.props_of("urn:hypermediator:Affordance"))
    assert affordances
    assert all("control" in item for item in affordances)
