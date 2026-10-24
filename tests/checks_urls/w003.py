"""Affordances selected for the Link header that have no rel."""

from django.http import HttpRequest, HttpResponse
from django.urls import URLPattern, URLResolver, path
from django.views import View

from hypermediator.affordances import Affordance
from hypermediator.views import HypermediaMixin, affordance


class SelectedNoRel(HypermediaMixin, View):
    affordance = Affordance("Selected", link_header=True)

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("selected")


class SelectedWithRel(HypermediaMixin, View):
    affordance = Affordance("Fine", rel=("help",), link_header=True)

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("fine")


class NotSelected(HypermediaMixin, View):
    affordance = Affordance("Quiet")

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("quiet")


@affordance(label="Selected fn", link_header=True)
def selected_fn(request: HttpRequest) -> HttpResponse:
    return HttpResponse("selected fn")


urlpatterns: list[URLPattern | URLResolver] = [
    path("s/", SelectedNoRel.as_view(), name="s-norel"),
    path("r/", SelectedWithRel.as_view(), name="s-rel"),
    path("q/", NotSelected.as_view(), name="s-quiet"),
    path("f/", selected_fn, name="s-fn"),
]
