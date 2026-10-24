"""A hypermediator view handles POST but declares no affordance."""

from django.http import HttpRequest, HttpResponse
from django.urls import URLPattern, URLResolver, path
from django.views import View

from hypermediator.views import HypermediaMixin


class PostNoAffordance(HypermediaMixin, View):
    def post(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("ok")


urlpatterns: list[URLPattern | URLResolver] = [
    path("p/", PostNoAffordance.as_view(), name="p-post"),
]
