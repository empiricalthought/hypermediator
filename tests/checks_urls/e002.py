"""An FBV declaration with an unavailable check but no model."""

from django.http import HttpRequest, HttpResponse
from django.urls import URLPattern, URLResolver, path

from hypermediator.views import affordance


@affordance(label="Close", unavailable=lambda request, obj: "no")
def close(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


urlpatterns: list[URLPattern | URLResolver] = [path("c/", close, name="close")]
