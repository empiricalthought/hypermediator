from collections.abc import Iterator

import pytest
from django.core.checks import CheckMessage, Error, Tags, Warning, run_checks
from django.test import override_settings

from hypermediator.endpoints import endpoint_for


def messages_for(urlconf: str | None = None) -> list[CheckMessage]:
    def run() -> list[CheckMessage]:
        return [
            m for m in run_checks(tags=[Tags.urls]) if (m.id or "").startswith("hypermediator.")
        ]

    if urlconf is None:
        return run()
    with override_settings(ROOT_URLCONF=urlconf):
        endpoint_for.cache_clear()
        return run()


@pytest.fixture(autouse=True)
def _clear_endpoint_cache() -> Iterator[None]:
    yield
    endpoint_for.cache_clear()


def test_w001_flags_put_on_update_view() -> None:
    (message,) = messages_for("tests.checks_urls.w001_put")
    assert isinstance(message, Warning)
    assert message.id == "hypermediator.W001"
    assert "RenameWidget" in message.msg
    assert "w-update" in message.msg
    assert "PUT" in message.msg
    assert message.hint == (
        'Set http_method_names = ["get", "post", "head", "options"] on the view, '
        "or declare an affordance for these methods."
    )


def test_w001_flags_post_without_affordance() -> None:
    (message,) = messages_for("tests.checks_urls.w001_post")
    assert message.id == "hypermediator.W001"
    assert "PostNoAffordance" in message.msg
    assert "POST" in message.msg


def test_w001_uses_namespaced_url_name() -> None:
    (message,) = messages_for("tests.checks_urls.nested")
    assert "inner:w-update" in message.msg


def test_w002_flags_fields_without_post_handler() -> None:
    (message,) = messages_for("tests.checks_urls.w002")
    assert isinstance(message, Warning)
    assert message.id == "hypermediator.W002"
    assert "FieldsNoPost" in message.msg
    assert "f-nopost" in message.msg


def test_w003_flags_link_header_without_rel() -> None:
    messages = messages_for("tests.checks_urls.w003")
    assert [m.id for m in messages] == ["hypermediator.W003", "hypermediator.W003"]
    assert all(isinstance(m, Warning) for m in messages)
    text = " ".join(m.msg for m in messages)
    assert "SelectedNoRel" in text
    assert "selected_fn" in text
    assert "s-norel" in text
    assert "has no rel" in text
    assert "SelectedWithRel" not in text


def test_e001_flags_unnamed_hypermediator_views() -> None:
    messages = messages_for("tests.checks_urls.e001")
    assert [m.id for m in messages] == ["hypermediator.E001", "hypermediator.E001"]
    assert all(isinstance(m, Error) for m in messages)


def test_e002_flags_unavailable_without_model() -> None:
    (message,) = messages_for("tests.checks_urls.e002")
    assert isinstance(message, Error)
    assert message.id == "hypermediator.E002"
    assert "close" in message.msg


def test_clean_project_has_no_messages() -> None:
    assert messages_for() == []
