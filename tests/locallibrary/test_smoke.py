"""Every LocalLibrary page renders for a librarian and conforms to layers 1 to 4."""

from typing import Any

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from catalog.models import Author, Book, BookInstance
from hypermediator.testing import assert_conforms


def test_every_page_renders(
    client: Client, librarian: User, author: Author, book: Book, on_loan_copy: BookInstance
) -> None:
    client.force_login(librarian)
    author_pk = {"pk": author.pk}
    book_pk = {"pk": book.pk}
    pages: list[tuple[str, dict[str, Any]]] = [
        ("index", {}),
        ("books", {}),
        ("book-detail", book_pk),
        ("authors", {}),
        ("author-detail", author_pk),
        ("my-borrowed", {}),
        ("all-borrowed", {}),
        ("renew-book-librarian", {"pk": on_loan_copy.pk}),
        ("author-create", {}),
        ("author-update", author_pk),
        ("author-delete", author_pk),
        ("book-create", {}),
        ("book-update", book_pk),
        ("book-delete", book_pk),
    ]
    for name, kwargs in pages:
        response = client.get(reverse(name, kwargs=kwargs))
        assert response.status_code == 200, name
        assert_conforms(response)
