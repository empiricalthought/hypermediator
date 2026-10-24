from pathlib import Path

from django.core.checks import Warning, run_checks
from django.test import override_settings

from hypermediator.lint import LintIssue, lint_source, lint_templates

MESSAGE = (
    "Hand-written link to affordance '{}'; use {{% hm_link %}}, {{% hm_action %}} or "
    "{{% hm_form %}} so see/use checks apply."
)


def test_url_tag_in_href_reported() -> None:
    source = "<p>\n<a class=x href='{% url \"widget-renew\" w.pk %}'>Renew</a>\n</p>"
    assert lint_source("t.html", source) == [
        LintIssue("t.html", 2, "widget-renew", MESSAGE.format("widget-renew"))
    ]


def test_url_tag_in_form_action_reported() -> None:
    source = """<form action="{% url 'widget-renew' 1 %}" method="post"></form>"""
    (issue,) = lint_source("t.html", source)
    assert issue.url_name == "widget-renew"
    assert issue.line == 1


def test_literal_path_reported() -> None:
    source = '<a href="/widget/3/renew/?next=/x/#top">Renew</a>'
    (issue,) = lint_source("t.html", source)
    assert issue.url_name == "widget-renew"
    assert issue.message == MESSAGE.format("widget-renew")


def test_tag_usage_clean() -> None:
    source = "{% load hypermediator %}{% hm_link 'widget-renew' obj %}{% hm_form 'widget-renew' %}"
    assert lint_source("t.html", source) == []


def test_non_affordance_url_clean() -> None:
    source = (
        "<a href=\"{% url 'widget-detail' 1 %}\">a</a>"
        '<a href="/widget/1/">b</a>'
        '<a href="/nowhere/">c</a>'
        '<a href="https://example.com/widget/1/renew/">d</a>'
        "<a href=\"{% url 'no-such-name' %}\">e</a>"
    )
    assert lint_source("t.html", source) == []


def test_lint_templates_walks_template_dirs() -> None:
    fixtures = Path(__file__).parent / "lint_fixtures"
    templates = [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [fixtures],
            "APP_DIRS": False,
        }
    ]
    with override_settings(TEMPLATES=templates):
        (issue,) = lint_templates()
    assert (issue.template, issue.line, issue.url_name) == ("bypass.html", 2, "widget-renew")


def test_project_templates_clean() -> None:
    assert lint_templates() == []


def test_warning_not_error() -> None:
    fixtures = Path(__file__).parent / "lint_fixtures"
    templates = [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [fixtures],
            "APP_DIRS": False,
        }
    ]
    with override_settings(TEMPLATES=templates):
        messages = run_checks(tags=["hypermediator_templates"])
    (message,) = messages
    assert isinstance(message, Warning)
    assert message.id == "hypermediator.W101"
    assert message.msg == MESSAGE.format("widget-renew")
    assert str(message.obj).endswith("bypass.html")
