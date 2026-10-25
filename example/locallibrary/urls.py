"""URL configuration for the LocalLibrary example."""

from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from django.views.generic import RedirectView

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("catalog/", include("catalog.urls")),
    path("", RedirectView.as_view(url="catalog/", permanent=True)),
    path("accounts/", include("django.contrib.auth.urls")),
]
