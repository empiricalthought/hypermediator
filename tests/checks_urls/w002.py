"""An affordance with form fields on a view with no post handler."""

from django.http import HttpRequest, HttpResponse
from django.urls import URLPattern, URLResolver, path
from django.views import View

from hypermediator.affordances import Affordance
from hypermediator.views import HypermediaMixin


class FieldsNoPost(HypermediaMixin, View):
    affordance = Affordance("Fill in")
    fields = ("name",)

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("form")


urlpatterns: list[URLPattern | URLResolver] = [
    path("f/", FieldsNoPost.as_view(), name="f-nopost"),
]
