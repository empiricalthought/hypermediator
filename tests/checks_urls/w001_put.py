"""An UpdateView declares an affordance but still handles PUT."""

from django.urls import URLPattern, URLResolver, path
from django.views.generic.edit import UpdateView

from hypermediator.affordances import Affordance
from hypermediator.views import HypermediaMixin
from tests.models import Widget


class RenameWidget(HypermediaMixin, UpdateView):  # type: ignore[type-arg]
    model = Widget
    fields = ("name",)
    affordance = Affordance("Rename")


urlpatterns: list[URLPattern | URLResolver] = [
    path("w/<int:pk>/", RenameWidget.as_view(), name="w-update"),
]
