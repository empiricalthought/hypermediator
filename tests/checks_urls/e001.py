"""Hypermediator views routed without a URL name."""

from django.urls import URLPattern, URLResolver, path

from tests import views

urlpatterns: list[URLPattern | URLResolver] = [
    path("a/", views.WidgetDetailView.as_view()),
    path("b/", views.widget_page_fbv),
]
