# Hypermediator: First Release Design

Oct 23, 2026 · @Steve

## Intent

Hypermediator is a Django package that makes HTML applications built for people, and enhanced with htmx, operable by agents as a matter of course. It implements [PRINCIPLES.md](../../PRINCIPLES.md); read that first. This document records how the package meets those principles inside Django, and what the first release must deliver.

The developer experience is the point. A developer builds an app the ordinary Django way, following the procedure of the MDN [LocalLibrary tutorial](https://developer.mozilla.org/en-US/docs/Learn_web_development/Extensions/Server-side/Django/Tutorial_local_library_website). The HTML and HTTP they get out conform to the principles instead of Django's defaults. Whatever extra knowledge that requires is written in Python (views and forms), never in templates.

## Success

The first release is done when LocalLibrary, rebuilt on hypermediator, lives in this repository as the example and test project, and its tests verify all four layers of PRINCIPLES.md using the hypermediator extractor.

LocalLibrary exercises every check:

| Flow | See it | Use it | Do it |
|---|---|---|---|
| Renew a loan (librarian) | `catalog.can_mark_returned` permission → 403 | Only copies on loan → 409 | Date not in past, at most 4 weeks ahead → 422 |
| Author create / update / delete | Model permissions → 403 | (as the app declares) | Form validation → 422; stale edit → 409 |
| My borrowed / All borrowed | Login / permission | — | — |

The author update flow is the demonstration of optimistic concurrency (two librarians editing the same author).

The layer tests cover LocalLibrary's own pages (the whole tutorial's app pages, including list pagination and the Book CRUD challenge). They do not cover `django.contrib.auth` pages (login, logout, password reset) or the admin, which keep Django's behaviour.

## Goals

1. Affordances declared once, as data, on the view that handles them, inspectable at runtime.
2. The three checks (see it, use it, do it) built on Django's existing hooks wherever one exists, each yielding a reason.
3. All four layers of PRINCIPLES.md implemented and verifiable: native controls, names and labels, rels and microdata, htmx.
4. An extractor that lists the affordances a response exposes, for use in application tests.
5. Optimistic concurrency for edit forms.
6. Developer feedback through Django system checks and a template linter.

## Non-goals

- An HTML-to-MCP bridge, agent client, or compact agent formats (HAL-FORMS, markdown digests). Deferred to a later, independent project; this one owes it only introspectable structure.
- WebMCP attributes.
- Testing human accessibility. The extractor checks that properties reach agents; it does not model a real browser.
- Supporting htmx 2 or other enhancement libraries.
- Typing application data. Hypermediator does not choose or know any application vocabulary.

## Anti-goals

These would make the release a failure even if it technically works:

- **Unapproved divergence from Django.** Every behaviour that departs from vanilla Django must appear in the Divergences table below with approval. Nothing is assumed because the principles imply it. In particular, `LoginRequiredMixin` keeps Django's redirect-to-login behaviour.
- **Forbidding hand-written HTML.** Templates may still contain hand-written links and forms. Using hypermediator in templates is the expected path; the linter reports bypasses but never blocks them.
- **Metadata in templates.** Rels, availability rules, reasons, placement and triggers are declared in Python. Templates stay about layout.
- **Implementing domain constraints.** Affordances describe and constrain an outward-facing interface (what a client sees, may submit, and gets back). Domain rules stay in models, as Django has them; the view states which rules gate this interface and in what words.
- **Microdata collisions.** Hypermediator's microdata must never capture, alter or preclude an application's own microdata.

## Constraints

- Python 3.14, Django 6.1 (as already scaffolded with uv, ruff, mypy strict, pytest-django).
- htmx 4 is the only supported enhancement library.
- Changes to the MDN procedure should be as small as possible: ideally imports, mixins, and the extra declarations hypermediator needs.

## Divergences from Django

| Divergence | Status |
|---|---|
| Invalid form submission returns 422, not 200, on views that opt into hypermediator only (not Django's auth views, the admin, or other views) | Approved |
| `Vary: HX-Request, HX-Request-Type` added to responses that may be served as a fragment | Approved |
| `LoginRequiredMixin` behaviour | Not changed (Django default) |
| `Allow` header | Not changed (Django derives it from handler methods); mismatches with declared affordances are reported by system checks and asserted by tests |

Any new divergence the builder finds necessary must be raised with Steve before it is built.

## Design decisions

### Where affordances live

An affordance is declared on the **view** that handles it. Both class-based and function-based views are supported in the first release, with equal capability: MDN writes `renew_book_librarian` as a function view with `@login_required` and `@permission_required`, and it stays one; the author CRUD views stay class-based. For function views the declaration and the use-it predicate are attached by decorator (or equivalent) rather than by mixin, and see it must be evaluable for a referencing page without dispatching the view, which means hypermediator needs access to the permission the view requires (Django's `@permission_required` does not expose it). The builder designs both APIs; system checks, the extractor and the linter cover both kinds of view.

The view already owns most of the facts:

| Fact | Source |
|---|---|
| Target | The view's URL pattern |
| Method | GET or POST, from what the view handles |
| Fields | The view's form class |
| Rel | Declared on the view |
| Trigger and placement | Declared on the view |
| Availability rules | The three checks, below |

### The three checks

The model is Apache Causeway's (one action, three predicates, each returning a reason), implemented through Django's hooks:

- **See it (authorization).** The view's existing permission declaration (`permission_required`, `has_permission()`), reused as-is. Runs when rendering and again on submit. Failure on render: the control is omitted. Failure on submit: Django's own 403.
- **Use it (availability).** New surface. A method on the view that takes the target object (and the request, via the view) and returns a reason or nothing. Runs when rendering and again on submit. Failure on render: the control renders disabled with its reason. Failure on submit: 409.
- **Do it (submission).** The view's form: `clean_<field>()` and `clean()` raising `ValidationError`, unchanged from MDN. Failure: 422, re-rendering the affected region with the user's values, the reason and the control that resolves it. A stale-state conflict returns 409 (see Optimistic concurrency).

How a disabled control is disabled is the application's choice (PRINCIPLES.md layer 1). Hypermediator supplies a default and attaches the reason with `aria-describedby`.

### Referencing affordances from other pages

Other pages show an affordance by reference, not by redefining it. Book detail lists each copy with Renew beside it: its template asks hypermediator for the Renew affordance bound to that copy, the way `{% url %}` asks for a URL. Hypermediator evaluates see it and use it for the current request and renders the control enabled, disabled with its reason, or not at all. The referencing page's own affordance set, as seen by the extractor, includes that control.

### Placement

Placement (which region a response replaces) is declared once on the view, **relative to the control** by default (e.g. "the item this control belongs to", htmx `closest …`), so the same declaration updates whatever the user acted on, on whichever page. A referencing page may override placement. This works when an item is rendered from one shared partial wherever it appears; a page that renders an item its own way needs an override or falls back to a full-page response. Without JavaScript, the POST completes and redirects as in MDN.

### Fragments

Fragments come from Django 6 template partials (`{% partialdef %}`, rendered as `template.html#name`). One pipeline chooses a full page or a partial from `HX-Request` and `HX-Request-Type`, and sets `Vary` with Django's `patch_vary_headers`. Redirects, retargeting and history use htmx response headers. Errors render as fragments, since htmx 4 swaps 4xx and 5xx bodies.

### Rels and microdata

- Rels are the application's, declared per affordance on the view. Registered rels go on `a` and `link` only where HTML allows them. Extension (URI) rels are mirrored into `Link` headers or a linkset.
- Hypermediator uses its own microdata item type, in its own namespace, only to carry affordance facts a machine needs and HTML cannot state natively (for example, an action's identity on its form, or its rel where HTML forbids one).
- **Requirement:** under microdata scoping, an `itemprop` belongs to its nearest `itemscope` ancestor. Hypermediator's items must never capture application properties (for instance by wrapping application content inside a hypermediator `itemscope`). The technique (property placement, `itemref`, etc.) is the builder's.

### Optimistic concurrency

No version field on the model.

- When rendering an edit form, the view adds a hidden field holding a fingerprint: a hash of the current values of the fields the form exposes.
- On POST, the view recomputes the fingerprint from the database. On mismatch it returns 409, re-rendering the form with the user's submitted values, a reason (e.g. "This author was changed by someone else since you opened the form"), the current stored values, and a fresh fingerprint; resubmitting resolves it.
- No `ETag` is sent and `If-Match` is ignored. The fingerprint describes the form, not the whole page (which varies by user and other data), so using it as a validator could produce wrong 304s; honouring `If-Match` would add an unapproved 412 path. The hidden field is the only mechanism.
- Known tradeoff, accepted: a change to a field the form does not expose does not conflict. Applications wanting stronger guarantees can add their own version field.

### htmx

`hx-*` attributes are derived from each affordance's trigger and placement and go only on native controls that already work (with `href` or `action`), or their containers, so htmx sends the same request as a browser without JavaScript.

### Extractor

An in-process HTML parser (my call: Python's standard-library `html.parser`, so no added dependency; the builder may change this if it proves too weak) that lists the affordances a response exposes: each link and form with its target, method, rel, accessible name, enabled or disabled state, disabled reason, fields and their labels, and hypermediator microdata. It is shipped in the package for application tests. Tests assert the affordance set a page exposes in a given state, and each layer's "Verified by" rules from PRINCIPLES.md run against that set. It does not attempt faithful browser accessibility-tree computation.

### Developer feedback

- **Django system checks** (`manage.py check`, also at `runserver`) warn when a view's handler methods and its declared affordances disagree (e.g. a `post` handler with no declared POST affordance, or the reverse), plus other declaration errors the builder finds worth catching.
- **Template linter** (first release): reports template code that subverts the package's intent, e.g. a hand-written `href`/`action` (literal or `{% url %}`) pointing at a view that declares an affordance, rendered outside hypermediator. Report only, never blocking.

### Shipping htmx

My call: the package ships a pinned copy of htmx 4 as a static file plus a template tag to include it. (htmx 4.0.0 shipped August 28, 2026; npm keeps it on the `next` tag until early 2027, so pinning avoids surprise upgrades.)

## Left to the builder

- The concrete Python API: names of mixins, attributes, decorators and template tags; how an affordance is declared on a view; how the use-it method is named.
- How see it is evaluated for a referencing page without dispatching the target view (e.g. instantiating it with `setup()` and calling `has_permission()`).
- Default disabled-control rendering and its override.
- Microdata vocabulary terms and namespace URI, within the non-capture requirement.
- Linkset support beyond `Link` headers.
- Where LocalLibrary lives in the repo and how it is wired into the test suite.
- Whether the template linter is a system check, a management command, or both.
- Whether failed problem responses also carry RFC 9457 problem-type identifiers (optional layer 3 semantics).
