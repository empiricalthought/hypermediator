from django.apps import apps


def test_app_is_installed() -> None:
    assert apps.is_installed("hypermediator")
