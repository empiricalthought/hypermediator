# Hypermediator

Makes the correct, machine-operable path the default in HTML applications built for people and enhanced with htmx. See [docs/PRINCIPLES.md](docs/PRINCIPLES.md).

## Using hypermediator

### Installation

Add the app and the middleware, and load the tags in your base template:

```python
INSTALLED_APPS = [..., "hypermediator"]
MIDDLEWARE = [..., "hypermediator.middleware.HypermediatorMiddleware"]  # after sessions and auth
```

```html
{% load hypermediator %}
<head>... {% hm_htmx %}</head>
```

`{% hm_htmx %}` emits the vendored, pinned htmx script tag (never a CDN).

### Declaring an affordance

On a class-based view, add `HypermediaMixin`, an `affordance`, and optionally `unavailable`
(a reason string while the control cannot be used now, else `None`). Permissions are the view's
own (`PermissionRequiredMixin`): a user without them does not see the control (see it), and a
submit gets 403.

```python
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

Render with `hypermediator.shortcuts.render`, a drop-in for Django's that adds `partial=`
rendering for htmx, `Vary`, and a 422 for an invalid form. Use `ConcurrencyMixin` (before
`HypermediaMixin`) on an `UpdateView` to carry a form fingerprint: a stale submit gets 409 with
the current values.

### Template tags

- `{% hm_link "url-name" obj %}`: a link affordance (hidden, enabled, or disabled with its reason).
- `{% hm_action "url-name" obj %}`: a POST affordance with no fields, as a one-button form.
- `{% hm_form "url-name" form obj %}`: a full form affordance with fingerprint and errors.
- `{% hm_item obj %}`: marks the root element of an item's shared partial (`data-hm-item`).
- `{% hm_htmx %}`: the vendored htmx script.

Rels, reasons, placement and triggers come from Python, never from the template.

### Testing

`hypermediator.testing` verifies the four layers against rendered responses:
`assert_conforms(response)` (and `violations(response)`), `assert_same_affordances(full, fragment)`,
`assert_allow_matches(client, path, url_name)`, and
`assert_get_does_not_change_state(client, path, exclude=())`. `tests/locallibrary` uses all of them.

### Checks and linter

`manage.py check` validates affordance declarations (`hypermediator.E001`, `E002`, `W001`,
`W002`). The template linter flags hand-written links that bypass an affordance
(`hypermediator.W101`) and runs alone with `manage.py check --tag hypermediator_templates`.

### Where it differs from Django

Exactly two things, both only on hypermediator views: an invalid form returns 422 instead of
200, and responses carry `Vary: HX-Request, HX-Request-Type`. Login redirects, `Allow`, auth
views and the admin behave as Django's do.

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
