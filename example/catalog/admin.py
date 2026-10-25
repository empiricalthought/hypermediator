from django.contrib import admin

from .models import Author, Book, BookInstance, Genre, Language

admin.site.register(Genre)
admin.site.register(Language)


class BooksInline(admin.TabularInline):  # type: ignore[type-arg]
    model = Book


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("last_name", "first_name", "date_of_birth", "date_of_death")
    fields = ("first_name", "last_name", ("date_of_birth", "date_of_death"))
    inlines = (BooksInline,)


class BooksInstanceInline(admin.TabularInline):  # type: ignore[type-arg]
    model = BookInstance


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("title", "author", "display_genre")
    inlines = (BooksInstanceInline,)


@admin.register(BookInstance)
class BookInstanceAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("book", "status", "borrower", "due_back", "id")
    list_filter = ("status", "due_back")

    fieldsets = (
        (None, {"fields": ("book", "imprint", "id")}),
        ("Availability", {"fields": ("status", "due_back", "borrower")}),
    )
