"""Fixtures for the LocalLibrary tests: one librarian, one member, and a small catalogue."""

import datetime

import pytest
from django.contrib.auth.models import Permission, User

from catalog.models import Author, Book, BookInstance, Genre, Language

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
def librarian(db: None) -> User:
    user = User.objects.create_user("librarian", password="librarian-test-password")
    user.user_permissions.set(
        Permission.objects.filter(
            content_type__app_label="catalog", codename__in=LIBRARIAN_PERMISSIONS
        )
    )
    return user


@pytest.fixture
def member(db: None) -> User:
    return User.objects.create_user("member", password="member-test-password")


@pytest.fixture
def author(db: None) -> Author:
    """An author with no books, so deleting is available."""
    return Author.objects.create(first_name="Octavia", last_name="Butler")


@pytest.fixture
def author_with_books(db: None) -> Author:
    return Author.objects.create(first_name="Ursula", last_name="Le Guin")


@pytest.fixture
def book(author_with_books: Author) -> Book:
    book = Book.objects.create(
        title="The Dispossessed",
        author=author_with_books,
        summary="An ambiguous utopia.",
        isbn="9780061054884",
        language=Language.objects.create(name="English"),
    )
    book.genre.add(Genre.objects.create(name="Science Fiction"))
    return book


@pytest.fixture
def on_loan_copy(book: Book, member: User) -> BookInstance:
    return BookInstance.objects.create(
        book=book,
        imprint="Harper Voyager, 1994",
        status="o",
        due_back=datetime.date.today() + datetime.timedelta(days=7),
        borrower=member,
    )


@pytest.fixture
def available_copy(book: Book) -> BookInstance:
    return BookInstance.objects.create(book=book, imprint="Harper Voyager, 1994", status="a")
