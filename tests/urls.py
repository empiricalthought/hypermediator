from django.urls import URLPattern, URLResolver, path

from tests import views

urlpatterns: list[URLPattern | URLResolver] = [
    path("widget/<int:pk>/", views.widget_detail, name="widget-detail"),
    path("widget/<int:pk>/renew/", views.WidgetRenew.as_view(), name="widget-renew"),
    path("widget/<int:pk>/renew-fn/", views.widget_renew_fbv, name="widget-renew-fbv"),
    path("widgets/", views.WidgetLoginOnly.as_view(), name="widget-list"),
    path("plain/", views.WidgetUndeclared.as_view(), name="widget-plain"),
]
