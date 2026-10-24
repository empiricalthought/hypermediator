# Hypermediator

Makes the correct, machine-operable path the default in HTML applications built for people and enhanced with htmx. See [docs/PRINCIPLES.md](docs/PRINCIPLES.md).

## Using hypermediator

### Installation

Add the app and the middleware, and make sure the `request` context processor is on (the tags
read the request from the template context):

```python
INSTALLED_APPS = [..., "hypermediator"]
MIDDLEWARE = [
    ...,
    "django.middleware.gzip.GZipMiddleware",  # if used: before (outside) hypermediator
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "hypermediator.middleware.HypermediatorMiddleware",  # after sessions, auth and GZip
    ...,
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",  # required
                ...,
            ],
        },
    },
]
```

`HypermediatorMiddleware` must sit after (inside) `GZipMiddleware`, since it reads the response
body. Every template that uses the tags needs `{% load hypermediator %}`, including templates
that extend one that already loads it:

```html
{% load hypermediator %}
<head>... {% hm_htmx %}</head>
```

`{% hm_htmx %}` emits the vendored, pinned htmx script tag (never a CDN).

Hypermediator views must be synchronous; `async def` views and async class-based handlers are
not supported.

### Declaring an affordance

On a class-based view, add `HypermediaMixin`, an `affordance`, and optionally `unavailable`
(a reason string while the control cannot be used now, else `None`). Permissions are the view's
own (`PermissionRequiredMixin`): a user without them does not see the control (see it), and a
submit gets 403.

```python
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.urls import reverse_lazy
from django.views.generic.edit import DeleteView

from hypermediator.affordances import Affordance, Placement
from hypermediator.views import HypermediaMixin


class AuthorDelete(HypermediaMixin, PermissionRequiredMixin, DeleteView):
    model = Author
    success_url = reverse_lazy("authors")
    permission_required = "catalog.delete_author"
    affordance = Affordance(label="Delete author", placement=Placement.PAGE)
    http_method_names = ["get", "post", "head", "options"]  # declare what the affordance allows

    def unavailable(self, obj):
        if isinstance(obj, Author) and obj.book_set.exists():
            return "Authors with books cannot be deleted."
        return None
```

The control then renders disabled with that reason (use it), and a submit gets 409.

On a function view, use the `affordance` decorator, which takes the same declaration:

```python
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from hypermediator.affordances import Placement
from hypermediator.shortcuts import render
from hypermediator.views import affordance


@login_required
@require_http_methods(["GET", "POST"])
@affordance(
    label="Renew",
    rel=("https://locallibrary.example/rels/renew",),
    placement=Placement.PAGE,
    permission="catalog.can_mark_returned",
    model=BookInstance,
    unavailable=on_loan_only,  # (request, obj) -> reason | None
    form_class=RenewBookForm,
)
def renew_book_librarian(request, pk): ...
```

A user without `permission` is sent to the login page when anonymous and gets 403 otherwise, as
with Django's `permission_required`. The URL kwargs that identify the object default to
`{"pk": obj.pk}`; pass `url_kwargs=lambda obj: {...}` for another route. Class-based views take
them from the route (`pk_url_kwarg`, else `slug_url_kwarg` and `slug_field`).

Render with `hypermediator.shortcuts.render`, a drop-in for Django's that adds `partial=`
rendering for htmx, `Vary`, and a 422 for an invalid form. Use `ConcurrencyMixin` (before
`HypermediaMixin`) on an `UpdateView` to carry a form fingerprint: a stale submit gets 409 with
the current values:

```python
from hypermediator.concurrency import ConcurrencyMixin


class AuthorUpdate(ConcurrencyMixin, HypermediaMixin, PermissionRequiredMixin, UpdateView): ...
```

For an htmx submit, a redirect returned by the view's handler becomes a 200 with `HX-Location`,
so htmx navigates to it, unless the request refreshes an item (`HX-Hm-Item`), whose redirect is
followed and swapped. Redirects from auth mixins and decorators are left as Django's.

### Template tags

Load them with `{% load hypermediator %}` in every template that uses them.

- `{% hm_link "url-name" obj %}`: a link affordance (hidden, enabled, or disabled with its reason).
- `{% hm_action "url-name" obj %}`: a POST affordance with no fields, as a one-button form.
- `{% hm_form "url-name" form obj %}`: a full form affordance with fingerprint and errors.
- `{% hm_item obj %}`: marks the root element of an item's shared partial (`data-hm-item`).
- `{% hm_htmx %}`: the vendored htmx script.

Rels, reasons, placement and triggers come from Python, never from the template.

### Testing

```python
from hypermediator.testing import (
    assert_allow_matches,
    assert_conforms,
    assert_get_does_not_change_state,
    assert_same_affordances,
)
```

`hypermediator.testing` verifies the four layers against rendered responses:
`assert_conforms(response)` (and `violations(response)`), `assert_same_affordances(full, fragment)`,
`assert_allow_matches(client, path, url_name)`, and
`assert_get_does_not_change_state(client, path, exclude=())` (which fails on any INSERT, UPDATE
or DELETE the GET issues outside the excluded models' tables). `tests/locallibrary` uses all of
them.

### Checks and linter

`manage.py check` validates affordance declarations (`hypermediator.E001`, `E002`, `W001`,
`W002`). The template linter flags hand-written links that bypass an affordance
(`hypermediator.W101`) and runs alone with `manage.py check --tag hypermediator_templates`.

### Where it differs from Django

- On hypermediator views, an invalid form returns 422 instead of 200.
- On hypermediator views, responses carry `Vary: HX-Request, HX-Request-Type`.
- `HypermediatorMiddleware`, which is opt-in, adds a `Link` response header listing the enabled
  affordances a response rendered that declare a rel.

Login redirects, `Allow`, auth views and the admin behave as Django's do.

### Running the example

`example/` is the MDN LocalLibrary tutorial rebuilt on hypermediator.

```bash
uv run python example/manage.py migrate
uv run python example/manage.py createsuperuser
uv run python example/manage.py runserver
uv run python example/manage.py check --tag hypermediator_templates
```

## Development

Requires [uv](https://docs.astral.sh/uv/). Python 3.14 and Django 6.1.

```bash
uv sync            # create .venv and install dependencies
uv run pytest      # tests
uv run ruff check  # lint
uv run ruff format # format
uv run mypy        # type-check
uv run bandit -c pyproject.toml -r src  # security scan
uv build           # build sdist and wheel
```
