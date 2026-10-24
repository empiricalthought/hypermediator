from django.urls import URLPattern, URLResolver, include, path

from tests import views

urlpatterns: list[URLPattern | URLResolver] = [
    path("widget/<int:pk>/", views.widget_detail, name="widget-detail"),
    path("widget/<int:pk>/renew/", views.WidgetRenew.as_view(), name="widget-renew"),
    path("widget/<int:pk>/renew-fn/", views.widget_renew_fbv, name="widget-renew-fbv"),
    path("widgets/", views.WidgetLoginOnly.as_view(), name="widget-list"),
    path("widget/new/", views.WidgetCreate.as_view(), name="widget-create"),
    path("widget/<int:pk>/edit/", views.WidgetUpdate.as_view(), name="widget-update"),
    path("widget/<int:pk>/delete/", views.WidgetDelete.as_view(), name="widget-delete"),
    path("widget/<int:pk>/view/", views.WidgetDetailView.as_view(), name="widget-view"),
    path("widget/<int:pk>/plain/", views.PlainDetailView.as_view(), name="widget-plain-view"),
    path("gadget/<uuid:pk>/renew/", views.gadget_renew, name="gadget-renew"),
    path(
        "ns/",
        include(
            ([path("<int:pk>/renew/", views.WidgetRenew.as_view(), name="renew")], "ns"),
            namespace="ns",
        ),
    ),
    path("pipeline/cbv/", views.PipelineCbv.as_view(), name="pipeline-cbv"),
    path("pipeline/fbv/", views.pipeline_fbv, name="pipeline-fbv"),
    path("pipeline/plain/", views.PlainFormView.as_view(), name="pipeline-plain"),
    path("plain/", views.WidgetUndeclared.as_view(), name="widget-plain"),
]
