from django.urls import URLPattern, URLResolver, include, path

from tests import views

urlpatterns: list[URLPattern | URLResolver] = [
    path("widget/<int:pk>/", views.widget_detail, name="widget-detail"),
    path("widget/<int:pk>/renew/", views.WidgetRenew.as_view(), name="widget-renew"),
    path("widget/<int:pk>/renew-fn/", views.widget_renew_fbv, name="widget-renew-fbv"),
    path("mutating/", views.mutating_get, name="mutating-get"),
    path("saving/", views.saving_get, name="saving-get"),
    path(
        "widget/by-name/<slug:slug>/renew/",
        views.WidgetRenewBySlug.as_view(),
        name="widget-renew-slug",
    ),
    path(
        "widget/by-name/<slug:name>/rename-fn/", views.widget_rename_fbv, name="widget-rename-fbv"
    ),
    path("widgets/guarded-fn/", views.widget_guarded_fbv, name="widget-guarded-fbv"),
    path("widgets/login-post/", views.WidgetLoginPost.as_view(), name="widget-login-post"),
    path("widgets/", views.WidgetLoginOnly.as_view(), name="widget-list"),
    path("widget/new/", views.WidgetCreate.as_view(), name="widget-create"),
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
    path("pipeline/cbv/", views.PipelineCbvStrict.as_view(), name="pipeline-cbv"),
    path("pipeline/fbv/", views.pipeline_fbv, name="pipeline-fbv"),
    path("pipeline/plain/", views.PlainFormView.as_view(), name="pipeline-plain"),
    path("widgets/next/", views.WidgetNext.as_view(), name="widget-next"),
    path("widgets/quiet/", views.WidgetQuiet.as_view(), name="widget-quiet"),
    path("widgets/page/", views.WidgetPage.as_view(), name="widget-page"),
    path("widgets/page-fn/", views.widget_page_fbv, name="widget-page-fbv"),
    path("renew-form/", views.RenewFormView.as_view(), name="renew-form"),
    path("widgets/odd/", views.WidgetOdd.as_view(), name="widget-odd"),
    path("plain/", views.WidgetUndeclared.as_view(), name="widget-plain"),
    path("widget/<int:pk>/edit-concurrent/", views.WidgetEdit.as_view(), name="widget-edit"),
    path("widget/<int:pk>/edit-all/", views.WidgetEditAll.as_view(), name="widget-edit-all"),
    path("thing/<int:pk>/edit/", views.ThingEdit.as_view(), name="thing-edit"),
    path("catalog/", include("catalog.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
]
