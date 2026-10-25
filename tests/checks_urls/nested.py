"""A namespaced include, to see namespaced names in messages."""

from django.urls import URLPattern, URLResolver, include, path

from tests.checks_urls import w001_put

urlpatterns: list[URLPattern | URLResolver] = [
    path("n/", include((w001_put.urlpatterns, "inner"), namespace="inner")),
]
