"""Every LocalLibrary page renders for a librarian and conforms to layers 1 to 4."""

import datetime
from typing import Any

import pytest
from django.contrib.auth.models import Permission, User
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse

from catalog.models import Author, Book, BookInstance, Genre, Language
from hypermediator.testing import assert_conforms

LIBRARIAN_PERMISSIONS = (
    "can_mark_returned",
    "add_author",
    "change_author",
    "delete_author",
    "add_book",
    "change_book",
    "delete_book",
)


@pytest.fixture
def library(db: Any) -> dict[str, Any]:
    librarian = User.objects.create_user("librarian", password="librarian-test-password")
    librarian.user_permissions.set(
        Permission.objects.filter(
            content_type__app_label="catalog", codename__in=LIBRARIAN_PERMISSIONS
        )
    )
    author = Author.objects.create(first_name="Ursula", last_name="Le Guin")
    book = Book.objects.create(
        title="The Dispossessed",
        author=author,
        summary="An ambiguous utopia.",
        isbn="9780061054884",
        language=Language.objects.create(name="English"),
    )
    book.genre.add(Genre.objects.create(name="Science Fiction"))
    on_loan = BookInstance.objects.create(
        book=book,
        imprint="Harper Voyager, 1994",
        status="o",
        due_back=datetime.date.today() + datetime.timedelta(days=7),
        borrower=librarian,
    )
    BookInstance.objects.create(book=book, imprint="Harper Voyager, 1994", status="a")
    return {"librarian": librarian, "author": author, "book": book, "on_loan": on_loan}


def test_every_page_renders(client: Client, library: dict[str, Any]) -> None:
    client.force_login(library["librarian"])
    author_pk = {"pk": library["author"].pk}
    book_pk = {"pk": library["book"].pk}
    pages: list[tuple[str, dict[str, Any]]] = [
        ("index", {}),
        ("books", {}),
        ("book-detail", book_pk),
        ("authors", {}),
        ("author-detail", author_pk),
        ("my-borrowed", {}),
        ("all-borrowed", {}),
        ("renew-book-librarian", {"pk": library["on_loan"].pk}),
        ("author-create", {}),
        ("author-update", author_pk),
        ("author-delete", author_pk),
        ("book-create", {}),
        ("book-update", book_pk),
        ("book-delete", book_pk),
    ]
    for name, kwargs in pages:
        response = client.get(reverse(name, kwargs=kwargs))
        assert isinstance(response, HttpResponse)
        assert response.status_code == 200, name
        assert_conforms(response)
