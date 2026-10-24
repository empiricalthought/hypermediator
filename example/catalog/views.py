import datetime
import uuid

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.models import AnonymousUser
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views import generic
from django.views.decorators.http import require_http_methods
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from hypermediator.affordances import Affordance, Placement
from hypermediator.concurrency import ConcurrencyMixin
from hypermediator.shortcuts import render
from hypermediator.views import HypermediaMixin, affordance

from .forms import RenewBookForm
from .models import Author, Book, BookInstance

# The edit views handle PUT (and DELETE) too; their affordances declare only GET and POST.
FORM_METHODS = ["get", "post", "head", "options"]


def index(request: HttpRequest) -> HttpResponse:
    """View function for home page of site."""
    # Generate counts of some of the main objects
    num_books = Book.objects.all().count()
    num_instances = BookInstance.objects.all().count()

    # Available books (status = 'a')
    num_instances_available = BookInstance.objects.filter(status__exact="a").count()

    # The 'all()' is implied by default.
    num_authors = Author.objects.count()

    # Number of visits to this view, as counted in the session variable.
    num_visits = request.session.get("num_visits", 0)
    num_visits += 1
    request.session["num_visits"] = num_visits

    context = {
        "num_books": num_books,
        "num_instances": num_instances,
        "num_instances_available": num_instances_available,
        "num_authors": num_authors,
        "num_visits": num_visits,
    }

    # Render the HTML template index.html with the data in the context variable
    return render(request, "catalog/index.html", context=context, partial="content")


class BookListView(HypermediaMixin, generic.ListView):  # type: ignore[type-arg]
    """Generic class-based view for a list of books."""

    model = Book
    paginate_by = 10
    partial = "content"


class BookDetailView(HypermediaMixin, generic.DetailView):  # type: ignore[type-arg]
    """Generic class-based detail view for a book."""

    model = Book
    partial = "content"


class AuthorListView(HypermediaMixin, generic.ListView):  # type: ignore[type-arg]
    """Generic class-based list view for a list of authors."""

    model = Author
    paginate_by = 10
    partial = "content"


class AuthorDetailView(HypermediaMixin, generic.DetailView):  # type: ignore[type-arg]
    """Generic class-based detail view for an author."""

    model = Author
    partial = "content"


class LoanedBooksByUserListView(HypermediaMixin, LoginRequiredMixin, generic.ListView):  # type: ignore[type-arg]
    """Generic class-based view listing books on loan to current user."""

    model = BookInstance
    template_name = "catalog/bookinstance_list_borrowed_user.html"
    paginate_by = 10
    partial = "content"

    def get_queryset(self) -> QuerySet[BookInstance]:
        user = self.request.user
        if isinstance(user, AnonymousUser):  # LoginRequiredMixin has already refused these
            return BookInstance.objects.none()
        return (
            BookInstance.objects.filter(borrower=user)
            .filter(status__exact="o")
            .order_by("due_back")
        )


class LoanedBooksAllListView(HypermediaMixin, PermissionRequiredMixin, generic.ListView):  # type: ignore[type-arg]
    """Generic class-based view listing all books on loan. Only visible to users with
    can_mark_returned permission."""

    model = BookInstance
    permission_required = "catalog.can_mark_returned"
    template_name = "catalog/bookinstance_list_borrowed_all.html"
    paginate_by = 10
    partial = "content"

    def get_queryset(self) -> QuerySet[BookInstance]:
        return BookInstance.objects.filter(status__exact="o").order_by("due_back")


def on_loan_only(request: HttpRequest, copy: BookInstance | None) -> str | None:
    """Renewing extends a loan, so only a copy on loan can be renewed."""
    if copy is None or copy.status != "o":
        return "Only copies on loan can be renewed."
    return None


@login_required
@require_http_methods(["GET", "POST"])
@affordance(
    label="Renew",
    rel=("https://locallibrary.example/rels/renew",),
    placement=Placement.PAGE,
    permission="catalog.can_mark_returned",
    model=BookInstance,
    unavailable=on_loan_only,
    form_class=RenewBookForm,
)
def renew_book_librarian(request: HttpRequest, pk: uuid.UUID) -> HttpResponse:
    """View function for renewing a specific BookInstance by librarian."""
    book_instance = get_object_or_404(BookInstance, pk=pk)

    # If this is a POST request then process the Form data
    if request.method == "POST":
        # Create a form instance and populate it with data from the request (binding):
        form = RenewBookForm(request.POST)

        # Check if the form is valid:
        if form.is_valid():
            # process the data in form.cleaned_data as required
            # (here we just write it to the model due_back field)
            book_instance.due_back = form.cleaned_data["renewal_date"]
            book_instance.save()

            # redirect to a new URL:
            return HttpResponseRedirect(reverse("all-borrowed"))

    # If this is a GET (or any other method) create the default form
    else:
        proposed_renewal_date = datetime.date.today() + datetime.timedelta(weeks=3)
        form = RenewBookForm(initial={"renewal_date": proposed_renewal_date})

    context = {
        "form": form,
        "book_instance": book_instance,
    }

    return render(request, "catalog/book_renew_librarian.html", context, partial="renew-form")


class AuthorCreate(HypermediaMixin, PermissionRequiredMixin, CreateView):  # type: ignore[type-arg]
    model = Author
    fields = ["first_name", "last_name", "date_of_birth", "date_of_death"]  # noqa: RUF012
    initial = {"date_of_death": "11/11/2023"}  # noqa: RUF012
    permission_required = "catalog.add_author"
    affordance = Affordance(label="Create author", rel=("create-form",), placement=Placement.PAGE)
    http_method_names = FORM_METHODS


class AuthorUpdate(
    ConcurrencyMixin,
    HypermediaMixin,
    PermissionRequiredMixin,
    UpdateView,  # type: ignore[type-arg]
):
    model = Author
    # Not recommended (potential security issue if more fields added)
    fields = "__all__"
    permission_required = "catalog.change_author"
    affordance = Affordance(label="Update author", rel=("edit",), placement=Placement.PAGE)
    http_method_names = FORM_METHODS


class AuthorDelete(HypermediaMixin, PermissionRequiredMixin, DeleteView):  # type: ignore[type-arg]
    model = Author
    success_url = reverse_lazy("authors")
    permission_required = "catalog.delete_author"
    affordance = Affordance(label="Delete author", placement=Placement.PAGE)
    http_method_names = FORM_METHODS

    def unavailable(self, obj: object | None) -> str | None:
        if isinstance(obj, Author) and obj.book_set.exists():
            return "Authors with books cannot be deleted."
        return None


class BookCreate(HypermediaMixin, PermissionRequiredMixin, CreateView):  # type: ignore[type-arg]
    model = Book
    fields = ["title", "author", "summary", "isbn", "genre", "language"]  # noqa: RUF012
    permission_required = "catalog.add_book"
    affordance = Affordance(label="Create book", rel=("create-form",), placement=Placement.PAGE)
    http_method_names = FORM_METHODS


class BookUpdate(
    ConcurrencyMixin,
    HypermediaMixin,
    PermissionRequiredMixin,
    UpdateView,  # type: ignore[type-arg]
):
    model = Book
    fields = ["title", "author", "summary", "isbn", "genre", "language"]  # noqa: RUF012
    permission_required = "catalog.change_book"
    affordance = Affordance(label="Update book", rel=("edit",), placement=Placement.PAGE)
    http_method_names = FORM_METHODS


class BookDelete(HypermediaMixin, PermissionRequiredMixin, DeleteView):  # type: ignore[type-arg]
    model = Book
    success_url = reverse_lazy("books")
    permission_required = "catalog.delete_book"
    affordance = Affordance(label="Delete book", placement=Placement.PAGE)
    http_method_names = FORM_METHODS

    def unavailable(self, obj: object | None) -> str | None:
        if isinstance(obj, Book) and obj.bookinstance_set.exists():
            return "Books with copies cannot be deleted."
        return None
