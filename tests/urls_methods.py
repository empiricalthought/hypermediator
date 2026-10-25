"""Views whose Django handlers go beyond their declared affordances (W001 would flag them)."""

from django.urls import URLPattern, URLResolver, path

from tests import views

urlpatterns: list[URLPattern | URLResolver] = [
    path("widget/<int:pk>/", views.widget_detail, name="widget-detail"),
    path("widget/<int:pk>/edit/", views.WidgetUpdate.as_view(), name="widget-update"),
    path("widget/<int:pk>/delete/", views.WidgetDelete.as_view(), name="widget-delete"),
    path("pipeline/cbv/", views.PipelineCbv.as_view(), name="pipeline-cbv"),
]
