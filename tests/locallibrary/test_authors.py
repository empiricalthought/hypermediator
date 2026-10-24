"""Author management: delete guards, stale updates, invalid input and Django's login redirect."""

import re

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from catalog.models import Author, Book
from hypermediator.testing import assert_conforms

FINGERPRINT = re.compile(
    r'name="_hm_fingerprint"[^>]*value="([^"]+)"|value="([^"]+)"[^>]*name="_hm_fingerprint"'
)


def _fingerprint(html: str) -> str:
    match = FINGERPRINT.search(html)
    assert match, "no fingerprint field in the form"
    return match.group(1) or match.group(2)


def _update_data(author: Author, fingerprint: str, **changes: str) -> dict[str, str]:
    data = {
        "first_name": author.first_name,
        "last_name": author.last_name,
        "date_of_birth": "",
        "date_of_death": "",
        "_hm_fingerprint": fingerprint,
    }
    return data | changes


def test_author_delete_disabled_when_books(
    client: Client, librarian: User, author_with_books: Author, book: Book
) -> None:
    client.force_login(librarian)
    page = assert_conforms(client.get(author_with_books.get_absolute_url()))
    [delete] = page.by_name("author-delete")
    assert not delete.enabled
    assert delete.reason == "Authors with books cannot be deleted."
    assert not delete.hx


def test_author_delete_enabled_without_books(
    client: Client, librarian: User, author: Author
) -> None:
    client.force_login(librarian)
    [delete] = assert_conforms(client.get(author.get_absolute_url())).by_name("author-delete")
    assert delete.enabled


def test_book_delete_disabled_when_copies(
    client: Client, librarian: User, book: Book, available_copy: object
) -> None:
    client.force_login(librarian)
    [delete] = assert_conforms(client.get(book.get_absolute_url())).by_name("book-delete")
    assert not delete.enabled
    assert delete.reason == "Books with copies cannot be deleted."


def test_author_delete_post_409(
    client: Client, librarian: User, author_with_books: Author, book: Book
) -> None:
    client.force_login(librarian)
    response = client.post(reverse("author-delete", kwargs={"pk": author_with_books.pk}))
    assert response.status_code == 409
    assert "Authors with books cannot be deleted." in response.content.decode()
    assert Author.objects.filter(pk=author_with_books.pk).exists()


def test_author_stale_update_409_then_resubmit_ok(
    client: Client, librarian: User, author: Author
) -> None:
    client.force_login(librarian)
    url = reverse("author-update", kwargs={"pk": author.pk})
    stale = _fingerprint(client.get(url).content.decode())
    Author.objects.filter(pk=author.pk).update(last_name="Changed Elsewhere")

    conflict = client.post(url, _update_data(author, stale, first_name="Octavia E."))
    assert conflict.status_code == 409
    assert Author.objects.get(pk=author.pk).first_name == "Octavia"

    fresh = _fingerprint(conflict.content.decode())
    assert fresh != stale
    author.refresh_from_db()
    resubmit = client.post(url, _update_data(author, fresh, first_name="Octavia E."))
    assert resubmit.status_code == 302
    assert Author.objects.get(pk=author.pk).first_name == "Octavia E."


def test_author_invalid_422(client: Client, librarian: User) -> None:
    client.force_login(librarian)
    response = client.post(reverse("author-create"), {"first_name": "", "last_name": ""})
    assert response.status_code == 422
    assert_conforms(response)
    assert not Author.objects.exists()


def test_anonymous_author_create_redirects_to_login(client: Client, db: None) -> None:
    url = reverse("author-create")
    response = client.post(url, {"first_name": "A", "last_name": "B"})
    assert response.status_code == 302
    assert response["Location"] == f"/accounts/login/?next={url}"
    assert not Author.objects.exists()
