"""Load demo data and two demo accounts for trying LocalLibrary locally.

Development only. Accounts:
- librarian / mjHxw4qIbxFu: can renew loans and edit authors and books.
- member / gIgDirq1GDTD: borrows two copies; sees only "My borrowed".
"""

import datetime
from typing import Any

from django.contrib.auth.models import Permission, User
from django.core.management.base import BaseCommand

from catalog.models import Author, Book, BookInstance, Genre, Language

DEMO_USERS = {"librarian": "mjHxw4qIbxFu", "member": "gIgDirq1GDTD"}
LIBRARIAN_PERMS = [
    "can_mark_returned",
    "add_author",
    "change_author",
    "delete_author",
    "add_book",
    "change_book",
    "delete_book",
]


class Command(BaseCommand):
    help = "Create demo users, authors, books and copies (idempotent)."

    def handle(self, *args: Any, **options: Any) -> None:
        users = {}
        for name, password in DEMO_USERS.items():
            user, _ = User.objects.get_or_create(username=name)
            user.set_password(password)
            user.save()
            users[name] = user
        # MDN's librarians are staff users; the sidebar's Staff section needs is_staff.
        users["librarian"].is_staff = True
        users["librarian"].save()
        users["librarian"].user_permissions.set(
            Permission.objects.filter(codename__in=LIBRARIAN_PERMS)
        )

        fantasy, _ = Genre.objects.get_or_create(name="Fantasy")
        scifi, _ = Genre.objects.get_or_create(name="Science Fiction")
        english, _ = Language.objects.get_or_create(name="English")
        le_guin, _ = Author.objects.get_or_create(
            first_name="Ursula",
            last_name="Le Guin",
            defaults={"date_of_birth": datetime.date(1929, 10, 21)},
        )
        pratchett, _ = Author.objects.get_or_create(
            first_name="Terry",
            last_name="Pratchett",
            defaults={"date_of_birth": datetime.date(1948, 4, 28)},
        )
        Author.objects.get_or_create(first_name="Unpublished", last_name="Writer")

        books = [
            ("A Wizard of Earthsea", le_guin, "9780547773742", fantasy),
            ("The Left Hand of Darkness", le_guin, "9780441478125", scifi),
            ("Guards! Guards!", pratchett, "9780062225757", fantasy),
        ]
        today = datetime.date.today()
        for title, author, isbn, genre in books:
            book, created = Book.objects.get_or_create(
                isbn=isbn,
                defaults={
                    "title": title,
                    "author": author,
                    "summary": f"Demo copy of {title}.",
                    "language": english,
                },
            )
            book.genre.set([genre])
            if created:
                BookInstance.objects.create(book=book, imprint="Demo Press", status="a")
                BookInstance.objects.create(
                    book=book,
                    imprint="Demo Press",
                    status="o",
                    due_back=today + datetime.timedelta(days=7),
                    borrower=users["member"],
                )
                BookInstance.objects.create(book=book, imprint="Demo Press", status="m")
        self.stdout.write(self.style.SUCCESS("Demo data ready."))
