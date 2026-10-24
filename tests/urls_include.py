"""Routes whose object kwargs are captured by an enclosing include()."""

from django.urls import URLPattern, URLResolver, include, path

from tests import views

urlpatterns: list[URLPattern | URLResolver] = [
    path(
        "lib/<int:pk>/",
        include([path("renew/", views.WidgetRenew.as_view(), name="inc-renew")]),
    ),
    path("widget/<int:pk>/", views.widget_detail, name="widget-detail"),
    path("odd/<int:ident>/", views.WidgetRenew.as_view(), name="odd-renew"),
]
