import uuid
from datetime import date

from django.conf import settings
from django.contrib import admin
from django.db import models
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower
from django.urls import reverse


class Genre(models.Model):
    """Model representing a book genre."""

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Enter a book genre (e.g. Science Fiction, French Poetry etc.)",
    )

    class Meta:
        constraints = (
            UniqueConstraint(
                Lower("name"),
                name="genre_name_case_insensitive_unique",
                violation_error_message="Genre already exists (case insensitive match)",
            ),
        )

    def __str__(self) -> str:
        """String for representing the Model object."""
        return self.name


class Language(models.Model):
    """Model representing a Language (e.g. English, French, Japanese, etc.)"""

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Enter the book's natural language (e.g. English, French, Japanese etc.)",
    )

    class Meta:
        constraints = (
            UniqueConstraint(
                Lower("name"),
                name="language_name_case_insensitive_unique",
                violation_error_message="Language already exists (case insensitive match)",
            ),
        )

    def __str__(self) -> str:
        """String for representing the Model object (in Admin site etc.)"""
        return self.name


class Book(models.Model):
    """Model representing a book (but not a specific copy of a book)."""

    title = models.CharField(max_length=200)
    # Foreign Key used because book can only have one author, but authors can have multiple books.
    author = models.ForeignKey("Author", on_delete=models.RESTRICT, null=True)
    summary = models.TextField(max_length=1000, help_text="Enter a brief description of the book")
    isbn = models.CharField(
        "ISBN",
        max_length=13,
        unique=True,
        # MDN's help text links "ISBN number"; a link inside a hypermediator form would be an
        # unmanaged control in the affordance's wrapper, so the reference is plain text here.
        help_text=(
            "13 Character ISBN number (see https://www.isbn-international.org/content/what-isbn)"
        ),
    )
    # ManyToManyField used because genre can contain many books. Books can cover many genres.
    genre = models.ManyToManyField(Genre, help_text="Select a genre for this book")
    language = models.ForeignKey("Language", on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ("title", "author")

    def __str__(self) -> str:
        """String for representing the Model object."""
        return self.title

    def get_absolute_url(self) -> str:
        """Returns the URL to access a particular book record."""
        return reverse("book-detail", args=[str(self.id)])

    @admin.display(description="Genre")
    def display_genre(self) -> str:
        """Create a string for the Genre. This is required to display genre in Admin."""
        return ", ".join(genre.name for genre in self.genre.all()[:3])


class BookInstance(models.Model):
    """Model representing a specific copy of a book (i.e. that can be borrowed from the library)."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        help_text="Unique ID for this particular book across whole library",
    )
    book = models.ForeignKey("Book", on_delete=models.RESTRICT, null=True)
    imprint = models.CharField(max_length=200)
    due_back = models.DateField(null=True, blank=True)
    borrower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    LOAN_STATUS = (
        ("m", "Maintenance"),
        ("o", "On loan"),
        ("a", "Available"),
        ("r", "Reserved"),
    )

    status = models.CharField(
        max_length=1,
        choices=LOAN_STATUS,
        blank=True,
        default="m",
        help_text="Book availability",
    )

    class Meta:
        ordering = ("due_back",)
        permissions = (("can_mark_returned", "Set book as returned"),)

    def __str__(self) -> str:
        """String for representing the Model object."""
        title = self.book.title if self.book else ""
        return f"{self.id} ({title})"

    def get_absolute_url(self) -> str:
        """The copy's book page: the tutorial names a bookinstance-detail route it never adds."""
        if self.book_id is None:
            return reverse("books")
        return reverse("book-detail", args=[str(self.book_id)])

    @property
    def is_overdue(self) -> bool:
        """Determines if the book is overdue based on due date and current date."""
        return bool(self.due_back and date.today() > self.due_back)


class Author(models.Model):
    """Model representing an author."""

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    date_of_death = models.DateField("died", null=True, blank=True)

    class Meta:
        ordering = ("last_name", "first_name")

    def __str__(self) -> str:
        """String for representing the Model object."""
        return f"{self.last_name}, {self.first_name}"

    def get_absolute_url(self) -> str:
        """Returns the URL to access a particular author instance."""
        return reverse("author-detail", args=[str(self.id)])
