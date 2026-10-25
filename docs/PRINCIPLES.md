# Hypermediator: Design Principles

Oct 17, 2026 · @Steve

Hypermediator does for agents what accessibility-aware frameworks do for assistive technology: it makes the correct, machine-operable path the default in HTML applications built for people and enhanced with htmx.

## Foundations

1. **People first; agents read the same HTML.** There is one representation. Agent accessibility is a property of the application people use, as human accessibility is.
2. **Affordances are declared once, as data.** Each link or action holds its request (rel, method, target, fields), trigger, placement (target region and swap) and availability rules, and is inspectable at runtime.
3. **Two methods; the target names the action.** An affordance's method is GET or POST, the only two an HTML form can submit, so a browser without JavaScript and a plain HTTP client send the same request. GET never changes state. Each state-changing action has its own target URI and its own form, so the URI, not the method, identifies the action. This trades HTTP's more precise methods for one request shape across every client.
4. **Every affordance passes three checks: see it, use it, do it.** The vocabulary is Apache Causeway's. *See it*: may this user perform it (authorization)? *Use it*: does the current state allow it now (availability)? *Do it*: is the submitted input valid and consistent with current state (submission)? The first two run when rendering and again on submit; the third runs only on submit. Each check is a distinct predicate that returns a reason, and each layer expresses the outcome in its own terms.
5. **Layers add; they never replace.** Each layer adds a capability the ones below lack, and works without the ones above it. The floor: an agent reading only the accessibility tree can operate the app.
6. **Agent accessibility is tested like human accessibility.** The framework ships an extractor that asserts which affordances a page exposes in a given state. Each layer's checks run against that set.

## Layers

Bottom up. Layers 1–3 serve people and agents alike; layer 4 serves people.

### 1. Native controls: operability by any client

Each of the three checks (foundation 4) has a native outcome and its own status code.

- **See it.** A permitted affordance renders as an `a`, `form` or `button` with a real `href` or `action`, working without JavaScript. One the user may not perform is omitted; submitting it anyway returns 403.
- **Use it.** A permitted affordance that the current state rules out renders disabled, carrying its reason (named in layer 2). How each control is disabled is the application's choice. Submitting it anyway returns 409.
- **Do it.** Field and cross-field checks run on submit. Invalid input returns 422, and a conflict with current state (a stale version, a taken value) returns 409. Either way the response re-renders the affected region with the user's values, the reason from the failed check, and the control that resolves it. The status code, the reason and the remedy together make the error self-describing; a machine-readable problem-type identifier is optional layer 3 semantics.
- **Verified by:** with JavaScript off, every enabled affordance can be followed or submitted; every form submits GET or POST, and no GET changes state; every enabled control has an `href` or `action`; each failed check returns its own status: 403, 409, or 422/409.

### 2. Names and labels: identification in words

- Accessible names, `<label>` associations and button text come from the affordance.
- A disabled control's reason is attached with `aria-describedby`, for screen readers and agents alike.
- **Verified by:** every control and field has a non-empty accessible name; every disabled control carries a described reason.

### 3. Rels and microdata: stable machine meaning

- Rels identify links by meaning, independent of wording or language. HTML carries only rel values valid for their element.
- Microdata types the data and carries extension semantics, including each action's meaning on its form. Selected affordances are mirrored into `Link` headers or linksets as URI rels, where IANA and extension rels are legal.
- The `Allow` header is derived from the declared affordances, per target URI: GET and HEAD where a representation or form is served, POST where an action is accepted, OPTIONS where answered.
- **Verified by:** HTML carries only rel values valid for their element; microdata matches its declared types; `Allow` equals the declared methods.

### 4. htmx: responsive interaction for people

- htmx 4 is the single supported enhancement library. `hx-*` attributes, derived from trigger and placement, go only on native controls that already work, or their containers, so htmx issues the same GET or POST to the same href or action.
- One pipeline, two shapes: full page or fragment is chosen from `HX-Request` and `HX-Request-Type`, fragments come from the same templates, and `Vary` is set accordingly.
- Redirects, retargeting and history go through htmx response headers. Errors render as fragments, since htmx 4 swaps 4xx and 5xx bodies.
- **Verified by:** `hx-*` appears only on native controls with an `href` or `action`, or their containers; fragment and full-page responses expose the same affordance set; `Vary` is present.
