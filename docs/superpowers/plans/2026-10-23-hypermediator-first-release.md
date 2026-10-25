# Hypermediator First Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship hypermediator's affordance model, three checks, renderers, extractor, developer checks and linter, proven by MDN LocalLibrary rebuilt on it with all four PRINCIPLES.md layers verified in tests.

**Architecture:** Affordances are frozen dataclasses declared on views: a mixin for class-based views, a decorator for function views. One resolver (`endpoints.py`) turns a URL name into an `Endpoint` that can run *see it* and *use it* for any request without dispatching. Template tags render bound affordances through overridable package templates, and record them on the request. Middleware mirrors them into `Link` headers. An in-process extractor parses rendered HTML back into controls, and `hypermediator.testing` runs each layer's "Verified by" rules over them.

**Tech Stack:** Python 3.14, Django 6.1 (template partials, system checks, `patch_vary_headers`), htmx 4 (vendored), stdlib `html.parser`, pytest-django, mypy strict, ruff.

**Spec:** `docs/superpowers/specs/2026-10-23-hypermediator-design.md` (read with `docs/PRINCIPLES.md`).

## Global Constraints

- Python `>=3.14`, Django `>=6.1`; no new runtime dependencies. The stdlib `html.parser` is the only parser.
- htmx 4 is the only enhancement library; vendored, pinned, never loaded from a CDN.
- Divergences from Django are exactly two: invalid form → **422** on hypermediator views only, and `Vary: HX-Request, HX-Request-Type` on hypermediator views. Anything else that departs from Django needs Steve's approval before it is built. `LoginRequiredMixin`, `Allow` derivation, auth views and admin keep Django's behaviour.
- Status codes: *see it* fail on submit → 403 (Django's `PermissionDenied`); *use it* fail on submit → 409; invalid input → 422; stale fingerprint → 409.
- No metadata in templates: rels, reasons, placement and triggers come from Python. The only template-side hypermediator markup is tag calls (`{% hm_link %}`, `{% hm_action %}`, `{% hm_form %}`, `{% hm_item %}`, `{% hm_htmx %}`).
- Hypermediator microdata uses itemtype `urn:hypermediator:Affordance` (constant `hypermediator.microdata.ITEMTYPE`). Its `itemscope` element never wraps application content.
- No `ETag` is emitted and `If-Match` is ignored.
- Existing tooling must pass on every commit: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`.

## Rendered HTML Contract

The extractor, template tags and tests all depend on this. `{id}` is `hm-{name}` or `hm-{name}-{pk}` when bound to an object, where `name` is the URL name.

- **Wrapper:** each rendered affordance is `<span class="hm-control" id="{id}">` (links and action buttons) or `<div class="hm-control" id="{id}">` (full forms). The wrapper contains the control, an optional reason element, and the microdata element, and nothing else.
- **Enabled link:** `<a id="{id}-c" href="{url}" [rel="{html-valid rels}"] [hx-get hx-target hx-swap hx-select hx-trigger]>{label}</a>`.
- **Disabled link:** `<a id="{id}-c" role="link" aria-disabled="true" aria-describedby="{id}-reason">{label}</a> (<small id="{id}-reason" class="hm-reason">{reason}</small>)`. No `href`, no `hx-*`.
- **Action button** (POST affordance with no form fields): `<form id="{id}-c" action="{url}" method="post" [rel] [hx-post …]>{csrf}<button type="submit">{label}</button></form>`. When disabled: same form with no `hx-*`, `<button type="submit" disabled aria-describedby="{id}-reason">`, and the reason markup (` (<small id="{id}-reason" class="hm-reason">{reason}</small>)`) after the form.
- **Full form** (`hm_form`): `<form id="{id}-c" action="{url}" method="post" hx-post="{url}" hx-target="#{id}" hx-swap="outerHTML" hx-select="#{id}">`, then `{csrf}`, the hidden fingerprint `<input type="hidden" name="_hm_fingerprint">` when present, non-field errors in `<div id="{id}-errors" role="alert">`, each field via Django's `{{ field.as_field_group }}` (which already wires `aria-describedby` to `{auto_id}_error` and `_helptext` in Django 6.1), then `<button type="submit">{label}</button>`. When unavailable, the button is disabled with `aria-describedby="{id}-reason"` and the same reason markup follows the form.
- **Reason markup:** the reason element is rendered only by the overridable `hypermediator/reason.html`. The default is ` (<small id="{id}-reason" class="hm-reason">{reason}</small>)`: a leading space and parentheses outside the element, so `aria-describedby` and the extractor read only the reason text. An override may change the element, class and surrounding text, but must keep a non-empty element with id `{id}-reason`.
- **Microdata**, last child of the wrapper: `<span hidden itemscope itemtype="urn:hypermediator:Affordance"><meta itemprop="name" content="{name}"><meta itemprop="control" content="{id}-c">` plus one `<meta itemprop="rel" content="{token}">` per rel token (IANA names and URIs alike) `</span>`.
- **Item marker:** `{% hm_item obj %}` outputs ` data-hm-item="{app_label}.{model_name}:{pk}"`, for the root element of an item's shared partial.

## Review Focus

1. **Referenced affordance whose target view requires login but declares no permission, viewed anonymously.** Expected: the control renders enabled and following it redirects to login (Django default), not hidden. Pinned in Task 3.
2. **htmx swap where the redirected response doesn't contain the item** (`hx-select` matches nothing). Expected: the item is not blanked, because the server sends `HX-Reswap: none` and the client keeps the old content. Pinned in Task 6.
3. **POST to an affordance whose object no longer exists** (copy deleted between render and submit). Expected: 404, not 409 or 500. Pinned in Task 3.
4. **Fingerprint field tampered or missing on POST.** Expected: treated as stale → 409 with the form re-rendered, never a 500 and never a silent overwrite. Pinned in Task 7.
5. **Same affordance rendered twice on one page for the same object** (e.g. book detail listing a copy twice through two partials). Expected: duplicate `id`s are reported by `hypermediator.testing` as a layer-2 violation rather than silently producing invalid `aria-describedby` targets. Pinned in Task 9.

---

### Task 1: Affordance model and rel vocabulary

**Files:**
- Create: `src/hypermediator/affordances.py`, `src/hypermediator/rels.py`
- Test: `tests/test_affordances.py`

**Interfaces:**
- Produces:
  - `Placement(target: str, swap: str = "outerHTML", select: str | None = None, push_url: bool = False)`, frozen. `Placement.ITEM` is a sentinel instance `Placement(target="closest [data-hm-item]", select="item")`, where `select="item"` means "the bound object's item selector". `Placement.PAGE` is `Placement(target="body", swap="innerHTML", select="body", push_url=True)`.
  - `Affordance(label: str, rel: tuple[str, ...] = (), placement: Placement | None = None, trigger: str | None = None)`, frozen. A `placement` of `None` resolves to `ITEM` when bound to an object and to `PAGE` otherwise. `__post_init__` raises `ValueError` for an empty label or for a rel token that is neither an IANA-style token (`^[a-z][a-z0-9.\-]*$`) nor an absolute URI (`urllib.parse` scheme present).
  - `rels.html_rels(tokens: Iterable[str], element: Literal["a", "form"]) -> tuple[str, ...]` keeps only the tokens HTML allows on that element. For `a`: alternate author bookmark external help license next nofollow noopener noreferrer opener prev privacy-policy search tag terms-of-service. For `form`: external help license next nofollow noopener noreferrer opener prev search.

- [ ] **Step 1: Write failing tests**

```python
def test_rel_tokens_validated():
    Affordance(label="Renew", rel=("edit", "https://locallibrary.example/rels/renew"))
    with pytest.raises(ValueError):
        Affordance(label="Renew", rel=("Not A Rel",))
    with pytest.raises(ValueError):
        Affordance(label="", rel=())


def test_html_rels_filters_per_element():
    assert html_rels(["next", "edit", "https://x.example/r"], "a") == ("next",)
    assert html_rels(["tag", "search"], "form") == ("search",)
```

- [ ] **Step 2:** Run `uv run pytest tests/test_affordances.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3:** Implement the two modules as specified in Interfaces.
- [ ] **Step 4:** Run `uv run pytest tests/test_affordances.py -v && uv run mypy`. Expected: PASS.
- [ ] **Step 5:** Commit with `git commit -m "feat: affordance and placement model with rel vocabulary"`.

### Task 2: Extractor

**Files:**
- Create: `src/hypermediator/extract.py`, `src/hypermediator/microdata.py` (`ITEMTYPE = "urn:hypermediator:Affordance"` only)
- Test: `tests/test_extract.py` (HTML strings written to the Rendered HTML Contract; no Django needed)

**Interfaces:**
- Produces:
  - `Field(name: str, label: str, type: str, required: bool, described_by: tuple[str, ...])`
  - `Control(kind: Literal["link", "form"], id: str | None, name: str | None, href: str | None, method: str, rel: tuple[str, ...], label: str, enabled: bool, reason: str | None, fields: tuple[Field, ...], hx: Mapping[str, str], wrapper_id: str | None)`
    - `name` comes from hypermediator microdata, joined by the `control` property, and is `None` for unmanaged controls.
    - `rel` is the union of the element's `rel` and the microdata rels.
    - `method` is `"GET"` for links, otherwise the uppercased form method, defaulting to `"GET"`.
  - `Page(controls: tuple[Control, ...], ids: Counter[str], text_by_id: Mapping[str, str], hx_elements: tuple[tuple[str, Mapping[str, str], bool], ...])`
    - `hx_elements` holds (tag, attrs, contains_native_control) for every element carrying `hx-*`.
    - `Page.by_name(name: str) -> list[Control]`.
  - `extract(html: str) -> Page`.
- Accessible name order: `aria-label`, then `aria-labelledby` text, then the element's text content. A form's label is its submit button's name. A field's label comes from `label[for]`, then a wrapping `<label>`, then `aria-label`.
- `enabled`: a link is enabled when it has `href` and no `aria-disabled="true"`. A form is enabled when it has an `action` and its submit button is not `disabled`.
- `reason`: the text of the elements named by `aria-describedby` on the link, or on the form's submit button.

- [ ] **Step 1: Write failing tests**
  - `test_enabled_link`: `name == "book-detail"`, `href == "/catalog/book/1/"`, `rel == ("https://locallibrary.example/rels/renew",)` comes from microdata, and `enabled`.
  - `test_disabled_link_reason`: `not enabled` and `reason == "Only copies on loan can be renewed."`.
  - `test_form_fields_and_labels`: field `renewal_date` has `label == "Renewal date"`, `required`, and `described_by == ("id_renewal_date_helptext",)`.
  - `test_disabled_submit_reason`.
  - `test_unmanaged_controls_have_no_name`.
  - `test_duplicate_ids_counted`: `page.ids["hm-x-c"] == 2`.
  - `test_hx_elements_recorded`.
- [ ] **Step 2:** Run `uv run pytest tests/test_extract.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement `extract` as an `html.parser.HTMLParser` subclass that builds a lightweight element tree, then derives the controls.
- [ ] **Step 4:** Run `uv run pytest tests/test_extract.py -v && uv run mypy`. Expected: PASS.
- [ ] **Step 5:** Commit with `git commit -m "feat: in-process affordance extractor"`.

### Task 3: View declarations, endpoints, and submit-time checks

**Files:**
- Create: `src/hypermediator/views.py`, `src/hypermediator/endpoints.py`, `src/hypermediator/templates/hypermediator/unavailable.html`
- Create: `tests/views.py` (test-only CBVs and FBVs plus a `Widget` model in `tests/models.py`); modify `tests/urls.py` and `tests/settings.py` (add `"tests"` to `INSTALLED_APPS` and the `django.contrib.sessions` and `messages` apps)
- Test: `tests/test_views.py`

**Interfaces:**
- Consumes: `Affordance`, `Placement` (Task 1).
- Produces:
  - `HypermediaMixin`, for class-based views:
    - Attributes: `affordance: Affordance | None = None`, `placements: Mapping[str, Placement] = {}` (overrides for affordances this page references), `partial: str | None = None` (used by Task 4).
    - `unavailable(self, obj: object | None) -> str | None` returns `None` by default.
    - `post()` runs `unavailable` on `self.get_object()` (if it is a `SingleObjectMixin`, else on `None`) before `super().post()`. A reason returns 409 via `unavailable_response`.
  - `affordance(*, label: str, rel=(), placement=None, trigger=None, permission: str | Sequence[str] | None = None, model: type[Model] | None = None, unavailable: Callable[[HttpRequest, object | None], str | None] | None = None, partial: str | None = None, placements: Mapping[str, Placement] | None = None)`, a decorator for function views.
    - Sets `func.hypermediator = FunctionDeclaration(...)`. `functools.wraps` copies `__dict__`, so outer `@login_required` keeps the attribute.
    - Enforces `permission`: a logged-in user without it gets `PermissionDenied` (403). This replaces MDN's `@permission_required(..., raise_exception=True)`.
    - On POST, it loads `model` by the `pk` kwarg (`get_object_or_404`) and runs `unavailable`, returning 409.
  - `unavailable_response(request, endpoint: Endpoint, obj, reason: str) -> HttpResponse`.
    - Renders `hypermediator/unavailable.html` with status 409. The body contains the disabled control, with the same wrapper `id` the page had, and a link to `obj.get_absolute_url()` when it exists.
    - For htmx requests it also sets `HX-Retarget: #{id}`, `HX-Reswap: outerHTML` and `HX-Reselect: #{id}`.
  - `Endpoint` (frozen), in `endpoints.py`:
    - Fields: `name: str`, `affordance: Affordance`, `methods: frozenset[str]` (declared: `{"GET"}` plus `"POST"` when the view handles POST), `has_fields: bool` (the view has a `form_class`, or the FBV declares a form).
    - `see(request, kwargs) -> bool`. For a CBV, it instantiates `view_class(**view_initkwargs)`, calls `setup(request, **kwargs)`, and calls `has_permission()` if present. `LoginRequiredMixin` alone means visible. For an FBV, it uses `request.user.has_perms`.
    - `use(request, kwargs, obj) -> str | None`.
    - `endpoint_for(url_name: str) -> Endpoint | None` returns `None` when the view declares no affordance. It resolves with `reverse` and `resolve`; results are cached per URL name.
    - `bind(request, url_name, obj=None, *, placement_override=None) -> Bound`.
  - `Bound(endpoint, url: str, obj, state: Literal["enabled", "disabled", "hidden"], reason: str | None, dom_id: str, placement: Placement)`. URL kwargs default to `{"pk": obj.pk}`.

- [ ] **Step 1: Write failing tests**
  - `test_cbv_post_without_permission_is_403`
  - `test_cbv_post_unavailable_is_409_with_reason_in_body`
  - `test_fbv_permission_403_and_unavailable_409`
  - `test_fbv_attribute_survives_login_required`
  - `test_bind_hidden_disabled_enabled`: one user per state; assert `.state` and `.reason`.
  - `test_bind_login_only_view_is_enabled_for_anonymous` (Review Focus 1).
  - `test_post_to_deleted_object_is_404` (Review Focus 3).
  - `test_unavailable_htmx_headers`: `HX-Retarget == "#hm-widget-renew-1"`.
- [ ] **Step 2:** Run `uv run pytest tests/test_views.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement as specified in Interfaces.
- [ ] **Step 4:** Run `uv run pytest -v && uv run mypy`. Expected: PASS.
- [ ] **Step 5:** Commit with `git commit -m "feat: affordance declarations with see/use checks on submit"`.

### Task 4: Response pipeline: 422, partials, Vary, htmx redirects

**Files:**
- Create: `src/hypermediator/shortcuts.py`, `src/hypermediator/htmx.py`
- Modify: `src/hypermediator/views.py` (`HypermediaMixin.render_to_response`, `form_invalid`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `HypermediaMixin`, `affordance` (Task 3).
- Produces:
  - `htmx.is_htmx(request) -> bool` (`HX-Request: true`) and `htmx.is_partial(request) -> bool` (`HX-Request-Type: partial`).
  - `shortcuts.render(request, template_name, context=None, *, partial: str | None = None, status: int | None = None) -> HttpResponse`.
    - It is a drop-in for `django.shortcuts.render`.
    - It renders `f"{template_name}#{partial}"` when `is_partial(request)` and `partial` is set.
    - Status is 422 when `status` is `None` and any bound `BaseForm` in the context has errors.
    - It always calls `patch_vary_headers(response, ("HX-Request", "HX-Request-Type"))`.
  - `HypermediaMixin` applies the same partial selection, Vary, and `form_invalid` → status 422.
  - Redirect handling, for htmx requests from hypermediator views:
    - A 3xx after a POST whose bound placement is `PAGE` becomes 200 with `HX-Location: {location}`.
    - Item placements let the fetch follow the redirect.
    - A followed response with no matching item gets `HX-Reswap: none`, set by the rendering of the referencing tag when its item is absent. This is Review Focus 2. The server can't know the client's item, so the implementation is: the control sends `HX-Hm-Item: {item key}` via `hx-headers`, and the middleware in Task 6 sets `HX-Reswap: none` when the response is 200, comes from an htmx request, and its body lacks `data-hm-item="{key}"`.

- [ ] **Step 1: Write failing tests**
  - `test_invalid_form_is_422_cbv_and_fbv`
  - `test_valid_get_is_200`
  - `test_partial_rendered_for_partial_request`: body equals the partial only.
  - `test_vary_header`: `{"HX-Request", "HX-Request-Type"} <= set(vary)`.
  - `test_page_placement_redirect_becomes_hx_location`
  - `test_plain_django_view_untouched`: a vanilla `FormView` still returns 200 on invalid input.
- [ ] **Step 2:** Run `uv run pytest tests/test_pipeline.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement as specified in Interfaces.
- [ ] **Step 4:** Run `uv run pytest -v && uv run mypy`. Expected: PASS.
- [ ] **Step 5:** Commit with `git commit -m "feat: response pipeline with 422, partials and Vary"`.

### Task 5: Template tags and package templates

**Files:**
- Create: `src/hypermediator/templatetags/__init__.py`, `src/hypermediator/templatetags/hypermediator.py`
- Create: `src/hypermediator/templates/hypermediator/link.html`, `action.html`, `form.html`, `microdata.html`
- Test: `tests/test_tags.py` (asserts through `extract()` from Task 2)

**Interfaces:**
- Consumes: `bind`, `Bound` (Task 3), `html_rels` (Task 1), `ITEMTYPE` (Task 2).
- Produces:
  - `{% hm_link "url-name" [obj] %}`
    - Renders a link to the affordance's URL. For POST affordances with fields, that link is the GET form page.
    - A `hidden` state renders nothing.
    - The placement is the referencing view's `placements[name]` (read from `context["view"]`, or the FBV declaration) or the affordance's own. `ITEM` emits `hx-target="closest [data-hm-item]"`, `hx-select='[data-hm-item="{key}"]'` and `hx-headers='{"HX-Hm-Item": "{key}"}'`.
  - `{% hm_action "url-name" [obj] %}` renders a POST affordance without fields as an action button.
  - `{% hm_form "url-name" form [obj] %}` renders the full form per the contract, passing the bound `form`.
  - `{% hm_item obj %}` renders the item marker.
  - Every tag appends its `Bound` to `request._hm_rendered: list[Bound]`.
  - Applications override the look by shadowing `hypermediator/*.html` (the "how a control is disabled" choice).

- [ ] **Step 1: Write failing tests**
  - `test_link_states`: a page renders one `hm_link` per state, and `extract()` shows a hidden one absent, a disabled one with its reason, and an enabled one with its href.
  - `test_link_rel_split`: `rel="next"` appears on `<a>`. `edit` and the URI appear only in microdata, and `Control.rel` contains all three.
  - `test_action_button_disabled`
  - `test_form_renders_errors_described_and_422_context`: the extracted field has `described_by` containing `id_renewal_date_error`.
  - `test_item_placement_attrs`
  - `test_placement_override_from_referencing_view`
  - `test_microdata_does_not_capture_app_props`: the app wraps output in `<div itemscope itemtype="https://schema.org/Book">` with `<span itemprop="name">`. A minimal microdata walk in the test confirms the Book's props are only `name`.
  - `test_rendered_recorded_on_request`
- [ ] **Step 2:** Run `uv run pytest tests/test_tags.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement as specified in Interfaces.
- [ ] **Step 4:** Run `uv run pytest -v && uv run mypy`. Expected: PASS.
- [ ] **Step 5:** Commit with `git commit -m "feat: template tags rendering bound affordances"`.

### Task 6: Middleware: Link header and missing-item reswap

**Files:**
- Create: `src/hypermediator/middleware.py`
- Modify: `tests/settings.py` (add `"hypermediator.middleware.HypermediatorMiddleware"` after `AuthenticationMiddleware`)
- Test: `tests/test_middleware.py`

**Interfaces:**
- Consumes: `request._hm_rendered` (Task 5).
- Produces: `HypermediatorMiddleware`.
  - For each enabled `Bound`, it appends `<{url}>; rel="{tokens joined by space}"` to `Link`, de-duplicated by (url, rel), skipping affordances with no rel.
  - It handles Review Focus 2 as described in Task 4.

- [ ] **Step 1: Write failing tests**
  - `test_link_header_lists_enabled_only`
  - `test_link_header_quotes_uri_rels`
  - `test_reswap_none_when_item_missing`
  - `test_no_reswap_when_item_present`
- [ ] **Step 2:** Run `uv run pytest tests/test_middleware.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement as specified in Interfaces.
- [ ] **Step 4:** Run `uv run pytest -v && uv run mypy`. Expected: PASS.
- [ ] **Step 5:** Commit with `git commit -m "feat: Link header middleware"`.

### Task 7: Optimistic concurrency

**Files:**
- Create: `src/hypermediator/concurrency.py`
- Test: `tests/test_concurrency.py`

**Interfaces:**
- Consumes: `HypermediaMixin` (Task 3), the `hm_form` hidden-field slot (Task 5).
- Produces:
  - `fingerprint(instance: Model, fields: Iterable[str]) -> str`: a SHA-256 hex digest of `json.dumps(model_to_dict(instance, fields), sort_keys=True, default=str)`.
  - `ConcurrencyMixin`, for `UpdateView`, placed before `HypermediaMixin`:
    - `get_form` adds the hidden `_hm_fingerprint` with an initial value computed from `self.object`.
    - `post` computes the stored fingerprint from a fresh DB fetch before the form binds. On mismatch, or a missing or garbled value, it returns 409.
    - The 409 renders the form with the submitted values and a non-field error. The message is fixed copy: `"This {verbose_name} was changed by someone else since you opened the form. Review the current values and submit again."`
    - The context also gets `hm_current` (dict of the stored values), and the form gets a fresh fingerprint.
  - `hm_form` shows "Current value: …" under each field whose `hm_current` value differs from the submitted one.

- [ ] **Step 1: Write failing tests**
  - `test_fingerprint_stable_and_field_scoped`
  - `test_stale_submit_is_409_keeps_user_values_and_shows_current`
  - `test_resubmit_with_fresh_fingerprint_succeeds`
  - `test_missing_or_tampered_fingerprint_is_409` (Review Focus 4)
  - `test_change_to_unexposed_field_does_not_conflict`
  - `test_no_etag_header`
- [ ] **Step 2:** Run `uv run pytest tests/test_concurrency.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement as specified in Interfaces.
- [ ] **Step 4:** Run `uv run pytest -v && uv run mypy`. Expected: PASS.
- [ ] **Step 5:** Commit with `git commit -m "feat: form-level optimistic concurrency"`.

### Task 8: Vendored htmx

**Files:**
- Create: `src/hypermediator/static/hypermediator/htmx.min.js`, `src/hypermediator/htmx.py` (append `HTMX_VERSION`, `HTMX_SHA256`)
- Modify: `src/hypermediator/templatetags/hypermediator.py` (add `{% hm_htmx %}`)
- Test: `tests/test_htmx_static.py`

**Interfaces:**
- Produces: `{% hm_htmx %}` renders `<script src="{% static 'hypermediator/htmx.min.js' %}" integrity="sha256-…" defer></script>`.

- [ ] **Step 1: Ask Steve to approve the download** of `https://cdn.jsdelivr.net/npm/htmx.org@<latest 4.0.x>/dist/htmx.min.js`, stating the exact version and size. Save it to the static path and record `HTMX_VERSION` and `HTMX_SHA256` (base64 SRI form).
- [ ] **Step 2: Write tests**
  - `test_vendored_file_matches_hash`
  - `test_tag_renders_integrity`
  - `test_version_is_4`: `HTMX_VERSION.startswith("4.")`
- [ ] **Step 3:** Run `uv run pytest tests/test_htmx_static.py -v`. Expected: PASS.
- [ ] **Step 4:** Commit with `git commit -m "feat: vendor pinned htmx 4"`.

### Task 9: `hypermediator.testing`: layer verification

**Files:**
- Create: `src/hypermediator/testing.py`
- Test: `tests/test_testing.py`

**Interfaces:**
- Consumes: `extract`, `Page`, `Control` (Task 2), `html_rels` (Task 1), `endpoint_for` (Task 3).
- Produces:
  - `violations(response: HttpResponse) -> list[str]`, with one message per failed rule:
    - **L1:** every enabled control has `href` or `action`; every form method is GET or POST.
    - **L2:** every control and field has a non-empty name; every disabled control has a non-empty reason; no duplicate `id` (Review Focus 5).
    - **L3:** `rel` on `a`/`form` is only `html_rels` for that element; every hypermediator microdata item has `name` and a `control` that resolves to an id on the page.
    - **L4:** `hx-*` appears only on `a[href]`, `form[action]` or `button` inside one, or on an element containing a native control; `Vary` includes `HX-Request` when the page contains any managed control.
  - `assert_conforms(response) -> Page`: raises `AssertionError` listing the violations, else returns the extracted page.
  - `assert_same_affordances(full: HttpResponse, fragment: HttpResponse) -> None`: compares the (name, state) multiset of managed controls that appear inside the fragment region.
  - `assert_allow_matches(client, path: str, url_name: str) -> None`: the `client.options(path)` `Allow` header, as a set, equals `endpoint.methods | {"HEAD", "OPTIONS"}`.
  - `assert_get_does_not_change_state(client, path) -> None`: snapshots `{model: count and max(pk)}` for all models before and after a GET.

- [ ] **Step 1: Write failing tests**, one per rule, each with a minimal violating HTML or response and a conforming one: `test_l1_*`, `test_l2_*` (including duplicate ids), `test_l3_*`, `test_l4_*`, `test_allow_matches`, `test_same_affordances`.
- [ ] **Step 2:** Run `uv run pytest tests/test_testing.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement as specified in Interfaces.
- [ ] **Step 4:** Run `uv run pytest -v && uv run mypy`. Expected: PASS.
- [ ] **Step 5:** Commit with `git commit -m "feat: layer verification helpers for application tests"`.

### Task 10: System checks

**Files:**
- Create: `src/hypermediator/checks.py`
- Modify: `src/hypermediator/apps.py` (`ready()` imports `checks`)
- Test: `tests/test_checks.py`

**Interfaces:**
- Consumes: `HypermediaMixin`, `FunctionDeclaration` (Task 3).
- Produces checks registered with `@register(Tags.urls)`, walking `get_resolver().url_patterns` recursively:
  - `hypermediator.W001`: a CBV has a `post` handler but its `affordance` is `None`.
  - `hypermediator.W002`: a CBV declares an affordance with fields but has no `post` handler.
  - `hypermediator.E001`: a hypermediator view is routed without a URL `name`.
  - `hypermediator.E002`: an FBV declaration has `unavailable` but no `model`.

- [ ] **Step 1: Write failing tests:** `test_w001`, `test_w002`, `test_e001`, `test_e002`, `test_clean_project_has_no_messages`. Each uses `override_settings(ROOT_URLCONF=...)` with a small urlconf module in `tests/checks_urls/`.
- [ ] **Step 2:** Run `uv run pytest tests/test_checks.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement as specified in Interfaces.
- [ ] **Step 4:** Run `uv run pytest -v && uv run mypy`. Expected: PASS.
- [ ] **Step 5:** Commit with `git commit -m "feat: system checks for affordance declarations"`.

### Task 11: Template linter

**Files:**
- Create: `src/hypermediator/lint.py`
- Modify: `src/hypermediator/checks.py` (register the linter check)
- Test: `tests/test_lint.py`, `tests/templates/lint/*.html`

**Interfaces:**
- Consumes: `endpoint_for` (Task 3).
- Produces:
  - `LintIssue(template: str, line: int, url_name: str, message: str)`.
  - `lint_source(name: str, source: str) -> list[LintIssue]` finds `href=` or `action=` attributes whose value contains `{% url "x" … %}` (either quote style), or a literal path that `resolve()` maps to a URL name with an endpoint. It reports `"Hand-written link to affordance '{x}'; use {% hm_link %}, {% hm_action %} or {% hm_form %} so see/use checks apply."`
  - `lint_templates() -> list[LintIssue]` walks every directory from the configured template engines' `DIRS` and app template dirs.
  - It is registered as a system check with custom tag `"hypermediator_templates"`, emitting `hypermediator.W101` warnings and never errors, so it can be run alone with `manage.py check --tag hypermediator_templates`.

- [ ] **Step 1: Write failing tests**
  - `test_url_tag_in_href_reported`
  - `test_literal_path_reported`
  - `test_tag_usage_clean`
  - `test_non_affordance_url_clean`: `{% url 'index' %}` produces no issue.
  - `test_warning_not_error`
- [ ] **Step 2:** Run `uv run pytest tests/test_lint.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement as specified in Interfaces.
- [ ] **Step 4:** Run `uv run pytest -v && uv run mypy`. Expected: PASS.
- [ ] **Step 5:** Commit with `git commit -m "feat: template linter for bypassed affordances"`.

### Task 12: LocalLibrary on hypermediator

**Files:**
- Create the `example/` tree, following the MDN tutorial's code with hypermediator substitutions:
  - `example/manage.py`
  - `example/locallibrary/{__init__,settings,urls}.py`
  - `example/catalog/{__init__,apps,models,admin,forms,views,urls}.py`
  - `example/catalog/migrations/0001_initial.py`
  - `example/catalog/templates/catalog/*.html`
  - `example/templates/{base_generic.html,registration/login.html}`
- Modify:
  - `pyproject.toml`: pytest `pythonpath = [".", "example"]`, mypy `files += ["example"]`, ruff `src += ["example"]`.
  - `tests/settings.py` and `tests/urls.py`: include `catalog`, `django.contrib.admin`, `staticfiles`, `messages`, `auth.urls` and `catalog.urls` at `/catalog/`.
- Test: `tests/locallibrary/test_smoke.py`

**Interfaces:**
- Consumes everything above.
- Models, verbatim from MDN:
  - `Genre`, `Language`, `Author`, `Book` (author FK with `on_delete=RESTRICT`).
  - `BookInstance`: UUID `id`, `status` one of `m`/`o`/`a`/`r` with default `m`, `due_back`, `borrower`, and `Meta.permissions = (("can_mark_returned", "Set book as returned"),)`.
- URL names, verbatim from MDN: `index`, `books`, `book-detail`, `authors`, `author-detail`, `my-borrowed`, `all-borrowed`, `renew-book-librarian` (`book/<uuid:pk>/renew/`), `author-create`, `author-update`, `author-delete`, `book-create`, `book-update`, `book-delete`.
- Hypermediator substitutions (the whole diff from MDN):
  - **`renew_book_librarian` stays a function view.**
    - It is decorated `@login_required @affordance(label="Renew", rel=("https://locallibrary.example/rels/renew",), permission="catalog.can_mark_returned", model=BookInstance, unavailable=on_loan_only)`.
    - `on_loan_only` returns `"Only copies on loan can be renewed."` unless `status == "o"`.
    - It uses `from hypermediator.shortcuts import render` with `partial="renew-form"`.
    - The form's MDN messages are kept: `"Invalid date - renewal in past"` and `"Invalid date - renewal more than 4 weeks ahead"`.
  - **Author views:**
    - `AuthorCreate(HypermediaMixin, PermissionRequiredMixin, CreateView)`: `affordance = Affordance(label="Create author", rel=("create-form",), placement=Placement.PAGE)`.
    - `AuthorUpdate(ConcurrencyMixin, HypermediaMixin, PermissionRequiredMixin, UpdateView)`: `rel=("edit",)`, label `"Update author"`.
    - `AuthorDelete(HypermediaMixin, PermissionRequiredMixin, DeleteView)`: label `"Delete author"`, `unavailable` returns `"Authors with books cannot be deleted."` when `obj.book_set.exists()`. This replaces MDN's try/except redirect.
    - Permissions are MDN's `catalog.add_author`, `catalog.change_author` and `catalog.delete_author`.
  - **Book views:** the same pattern for book create, update and delete, with `catalog.add_book`, `catalog.change_book` and `catalog.delete_book`.
  - **List and detail views** add `HypermediaMixin` (page-only, with `affordance = None`) and `partial = "content"`. Pagination stays MDN's plain `<a href="?page=N" rel="prev|next">` links. A view with no affordance has no endpoint (`endpoint_for` returns `None`), so the linter doesn't flag these links.
  - **Templates:**
    - All of them use `{% hm_link %}`, `{% hm_action %}` and `{% hm_form %}`.
    - The copy row is one partial, `catalog/_bookinstance.html`, with `{% hm_item copy %}`. It is included by `book_detail.html`, `bookinstance_list_borrowed_user.html` and `bookinstance_list_borrowed_all.html`, and it carries `{% hm_link "renew-book-librarian" copy %}`.
    - `base_generic.html` includes `{% hm_htmx %}`.
    - Application schema.org microdata goes on `Book` and `Person`, to exercise the non-capture rule.
  - `manage.py check --tag hypermediator_templates` reports no warnings for the example's templates.
- [ ] **Step 1: Write the failing smoke test**: `test_every_page_renders` hits each GET URL name as a librarian and asserts 200 and `assert_conforms`.
- [ ] **Step 2:** Run `uv run pytest tests/locallibrary/test_smoke.py -v`. Expected: FAIL.
- [ ] **Step 3:** Build the example as specified.
- [ ] **Step 4:** Run `uv run pytest -v && uv run mypy && uv run ruff check`, and `cd example && uv run python manage.py check --tag hypermediator_templates`. Expected: PASS, with no warnings.
- [ ] **Step 5:** Commit with `git commit -m "feat: LocalLibrary example built on hypermediator"`.

### Task 13: LocalLibrary layer and flow tests

**Files:**
- Test: `tests/locallibrary/conftest.py` (fixtures: `librarian` with `can_mark_returned` and the author and book perms, `member`, `on_loan_copy`, `available_copy`, `author_with_books`, `author`), `tests/locallibrary/test_renew.py`, `test_authors.py`, `test_pages.py`

**Interfaces:**
- Consumes: `hypermediator.testing` (Task 9), the example (Task 12).

- [ ] **Step 1: Write the tests**
  - **Renew, see it:**
    - `test_renew_hidden_for_member`: `page.by_name("renew-book-librarian") == []` on book detail.
    - `test_renew_post_member_403`
  - **Renew, use it:**
    - `test_renew_disabled_for_available_copy_with_reason`: `reason == "Only copies on loan can be renewed."`.
    - `test_renew_post_available_copy_409`
  - **Renew, do it:**
    - `test_renew_past_date_422`: the extracted field reason contains `"Invalid date - renewal in past"`.
    - `test_renew_over_4_weeks_422`
    - `test_renew_valid_redirects_to_all_borrowed`
  - **Renew, htmx:**
    - `test_renew_link_item_placement_attrs`
    - `test_renew_htmx_partial_matches_full`: uses `assert_same_affordances`.
  - **Authors:**
    - `test_author_delete_disabled_when_books`
    - `test_author_delete_post_409`
    - `test_author_stale_update_409_then_resubmit_ok`
    - `test_author_invalid_422`
    - `test_anonymous_author_create_redirects_to_login`: Django's default is unchanged.
  - **Pages:**
    - `test_all_pages_conform_per_role`: anonymous, member and librarian; every GET page passes `assert_conforms`.
    - `test_allow_matches_on_affordance_urls`
    - `test_gets_do_not_change_state`
    - `test_link_header_on_book_detail`
    - `test_vary_on_hypermediator_pages`
    - `test_schema_org_book_props_not_captured`
- [ ] **Step 2:** Run `uv run pytest tests/locallibrary -v`. Expected: PASS. Any failure is a defect in Tasks 1–12: fix it there with a regression test in that task's test file, not by weakening these tests.
- [ ] **Step 3:** Update `README.md` with a "Using hypermediator" section: installation (app, middleware, `{% hm_htmx %}`), a CBV and an FBV declaration taken from the example, the template tags, `hypermediator.testing`, and the two divergences.
- [ ] **Step 4:** Run `uv run pytest && uv run ruff check && uv run ruff format --check && uv run mypy`. Expected: all PASS.
- [ ] **Step 5:** Commit with `git commit -m "test: verify LocalLibrary across all four layers"`.
