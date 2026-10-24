"""Renewing a loan across see it, use it, do it and htmx."""

import datetime

from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from catalog.models import Book, BookInstance
from hypermediator.extract import extract
from hypermediator.testing import assert_conforms, assert_same_affordances


def _renew_url(copy: BookInstance) -> str:
    return reverse("renew-book-librarian", kwargs={"pk": copy.pk})


def _in_days(days: int) -> str:
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


# See it


def test_renew_hidden_for_member(
    client: Client, member: User, book: Book, on_loan_copy: BookInstance
) -> None:
    client.force_login(member)
    response = client.get(book.get_absolute_url())
    assert response.status_code == 200
    assert assert_conforms(response).by_name("renew-book-librarian") == []


def test_renew_post_member_403(client: Client, member: User, on_loan_copy: BookInstance) -> None:
    client.force_login(member)
    response = client.post(_renew_url(on_loan_copy), {"renewal_date": _in_days(14)})
    assert response.status_code == 403
    on_loan_copy.refresh_from_db()
    assert on_loan_copy.due_back == datetime.date.fromisoformat(_in_days(7))


# Use it


def test_renew_disabled_for_available_copy_with_reason(
    client: Client, librarian: User, book: Book, available_copy: BookInstance
) -> None:
    client.force_login(librarian)
    page = assert_conforms(client.get(book.get_absolute_url()))
    [renew] = page.by_name("renew-book-librarian")
    assert not renew.enabled
    assert renew.reason == "Only copies on loan can be renewed."


def test_renew_post_available_copy_409(
    client: Client, librarian: User, available_copy: BookInstance
) -> None:
    client.force_login(librarian)
    response = client.post(_renew_url(available_copy), {"renewal_date": _in_days(7)})
    assert response.status_code == 409
    available_copy.refresh_from_db()
    assert available_copy.due_back is None


# Do it


def test_renew_past_date_422(client: Client, librarian: User, on_loan_copy: BookInstance) -> None:
    client.force_login(librarian)
    response = client.post(_renew_url(on_loan_copy), {"renewal_date": _in_days(-1)})
    assert response.status_code == 422
    page = extract(response.content.decode())
    assert "Invalid date - renewal in past" in page.text_by_id["id_renewal_date_error"]


def test_renew_over_4_weeks_422(
    client: Client, librarian: User, on_loan_copy: BookInstance
) -> None:
    client.force_login(librarian)
    response = client.post(_renew_url(on_loan_copy), {"renewal_date": _in_days(29)})
    assert response.status_code == 422
    page = extract(response.content.decode())
    assert (
        "Invalid date - renewal more than 4 weeks ahead" in page.text_by_id["id_renewal_date_error"]
    )


def test_renew_valid_redirects_to_all_borrowed(
    client: Client, librarian: User, on_loan_copy: BookInstance
) -> None:
    client.force_login(librarian)
    new_date = datetime.date.today() + datetime.timedelta(days=14)
    response = client.post(_renew_url(on_loan_copy), {"renewal_date": new_date.isoformat()})
    assert response.status_code == 302
    assert response["Location"] == reverse("all-borrowed")
    on_loan_copy.refresh_from_db()
    assert on_loan_copy.due_back == new_date


# htmx


def test_renew_link_page_placement_attrs(
    client: Client, librarian: User, book: Book, on_loan_copy: BookInstance
) -> None:
    client.force_login(librarian)
    response = client.get(book.get_absolute_url())
    [renew] = assert_conforms(response).by_name("renew-book-librarian")
    assert renew.enabled
    assert renew.hx["hx-target"] == "body"
    assert renew.hx["hx-push-url"] == "true"
    # The copy row is still the item: its root carries the marker.
    assert f'data-hm-item="catalog.bookinstance:{on_loan_copy.pk}"' in response.content.decode()


def test_renew_htmx_partial_matches_full(
    client: Client, librarian: User, book: Book, on_loan_copy: BookInstance
) -> None:
    client.force_login(librarian)
    url = book.get_absolute_url()
    full = client.get(url)
    fragment = client.get(url, headers={"HX-Request": "true", "HX-Request-Type": "partial"})
    assert fragment.status_code == 200
    assert_same_affordances(full, fragment)
