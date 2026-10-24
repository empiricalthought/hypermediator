from hypermediator.extract import extract

RENEW = "https://locallibrary.example/rels/renew"


def _meta(name: str, control: str, *rels: str) -> str:
    metas = "".join(f'<meta itemprop="rel" content="{rel}">' for rel in rels)
    return (
        '<span hidden itemscope itemtype="urn:hypermediator:Affordance">'
        f'<meta itemprop="name" content="{name}">'
        f'<meta itemprop="control" content="{control}">{metas}</span>'
    )


ENABLED_LINK = (
    '<span class="hm-control" id="hm-book-detail-1">'
    '<a id="hm-book-detail-1-c" href="/catalog/book/1/" hx-get="/catalog/book/1/" '
    'hx-target="#main" hx-swap="innerHTML">Details</a>'
    + _meta("book-detail", "hm-book-detail-1-c", RENEW)
    + "</span>"
)

DISABLED_LINK = (
    '<span class="hm-control" id="hm-renew-1">'
    '<a id="hm-renew-1-c" role="link" aria-disabled="true" aria-describedby="hm-renew-1-reason">'
    "Renew</a>"
    '<span id="hm-renew-1-reason" class="hm-reason">Only copies on loan can be renewed.</span>'
    + _meta("renew", "hm-renew-1-c")
    + "</span>"
)

FORM = (
    '<div class="hm-control" id="hm-renew-form">'
    '<form id="hm-renew-form-c" action="/renew/" method="post" hx-post="/renew/" '
    'hx-target="#hm-renew-form" hx-swap="outerHTML" hx-select="#hm-renew-form">'
    '<input type="hidden" name="csrfmiddlewaretoken" value="x">'
    '<input type="hidden" name="_hm_fingerprint" value="abc">'
    '<div id="hm-renew-form-errors" role="alert"></div>'
    "<div>"
    '<label for="id_renewal_date">Renewal date:</label>'
    '<div class="helptext" id="id_renewal_date_helptext">Up to 4 weeks.</div>'
    '<input type="date" name="renewal_date" id="id_renewal_date" required '
    'aria-describedby="id_renewal_date_helptext">'
    "</div>"
    '<div><label>Note <textarea name="note" aria-label="ignored"></textarea></label></div>'
    '<button type="submit">Renew book</button>'
    "</form>" + _meta("renew-form", "hm-renew-form-c", "nofollow") + "</div>"
)

DISABLED_SUBMIT = (
    '<span class="hm-control" id="hm-return-1">'
    '<form id="hm-return-1-c" action="/return/" method="post">'
    '<input type="hidden" name="csrfmiddlewaretoken" value="x">'
    '<button type="submit" disabled aria-describedby="hm-return-1-reason">Return</button>'
    "</form>"
    '<span id="hm-return-1-reason" class="hm-reason">Already returned.</span>'
    + _meta("return", "hm-return-1-c")
    + "</span>"
)


def test_enabled_link() -> None:
    (control,) = extract(ENABLED_LINK).by_name("book-detail")
    assert control.kind == "link"
    assert control.id == "hm-book-detail-1-c"
    assert control.wrapper_id == "hm-book-detail-1"
    assert control.href == "/catalog/book/1/"
    assert control.method == "GET"
    assert control.rel == (RENEW,)
    assert control.label == "Details"
    assert control.enabled
    assert control.reason is None
    assert control.hx == {
        "hx-get": "/catalog/book/1/",
        "hx-target": "#main",
        "hx-swap": "innerHTML",
    }


def test_disabled_link_reason() -> None:
    (control,) = extract(DISABLED_LINK).by_name("renew")
    assert not control.enabled
    assert control.href is None
    assert control.reason == "Only copies on loan can be renewed."
    assert control.hx == {}


def test_form_fields_and_labels() -> None:
    page = extract(FORM)
    (control,) = page.by_name("renew-form")
    assert control.kind == "form"
    assert control.method == "POST"
    assert control.href == "/renew/"
    assert control.label == "Renew book"
    assert control.enabled
    assert control.rel == ("nofollow",)
    assert control.hx["hx-post"] == "/renew/"
    assert [f.name for f in control.fields] == ["renewal_date", "note"]
    date, note = control.fields
    assert date.label == "Renewal date"
    assert date.type == "date"
    assert date.required
    assert date.described_by == ("id_renewal_date_helptext",)
    assert note.label == "Note"
    assert note.type == "textarea"
    assert not note.required
    assert note.described_by == ()
    assert page.text_by_id["hm-renew-form-errors"] == ""
    assert page.text_by_id["id_renewal_date_helptext"] == "Up to 4 weeks."


def test_disabled_submit_reason() -> None:
    (control,) = extract(DISABLED_SUBMIT).by_name("return")
    assert not control.enabled
    assert control.label == "Return"
    assert control.reason == "Already returned."
    assert control.fields == ()


def test_unmanaged_controls_have_no_name() -> None:
    page = extract(
        '<a href="/x/" aria-label="Exit">x</a>'
        '<form action="/y/"><button type="submit">Go</button></form>'
        "<a>bare</a>"
    )
    link, form, bare = page.controls
    assert (link.name, link.wrapper_id, link.label) == (None, None, "Exit")
    assert (form.name, form.method, form.enabled, form.label) == (None, "GET", True, "Go")
    assert not bare.enabled
    assert page.by_name("x") == []


def test_aria_labelledby_label() -> None:
    page = extract('<span id="l">Long   name</span><a href="/" aria-labelledby="l">ignored</a>')
    assert page.controls[0].label == "Long name"


def test_duplicate_ids_counted() -> None:
    assert extract(ENABLED_LINK).ids["hm-book-detail-1"] == 1
    dup = extract('<p id="hm-x-c">a<p id="hm-x-c">b<ul><li>one<li>two</ul>')
    assert dup.ids["hm-x-c"] == 2


def test_hx_elements_recorded() -> None:
    page = extract(
        '<div hx-boost="true"><p>text</p></div>'
        '<div hx-get="/a/"><a href="/a/">go</a></div>'
        '<br><input hx-post="/z/" name="q"><span hx-get="/b/">no</span>'
    )
    assert page.hx_elements == (
        ("div", {"hx-boost": "true"}, False),
        ("div", {"hx-get": "/a/"}, True),
        ("input", {"hx-post": "/z/"}, True),
        ("span", {"hx-get": "/b/"}, False),
    )
