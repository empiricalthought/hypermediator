"""Test-only views declaring affordances."""

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.views import View
from django.views.generic.detail import SingleObjectMixin

from hypermediator.affordances import Affordance
from hypermediator.views import HypermediaMixin, affordance
from tests.models import Widget


def retired_reason(widget: Widget | None) -> str | None:
    return "Retired widgets cannot be renewed" if widget and widget.status == "retired" else None


class RenewPost(View):
    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponseBase:
        return HttpResponse("renewed")


class WidgetRenew(PermissionRequiredMixin, HypermediaMixin, SingleObjectMixin, RenewPost):  # type: ignore[type-arg]
    model = Widget
    permission_required = "tests.change_widget"
    raise_exception = True
    affordance = Affordance("Renew", rel=("edit",))

    def unavailable(self, obj: object | None) -> str | None:
        return retired_reason(obj) if isinstance(obj, Widget) else None


class WidgetLoginOnly(LoginRequiredMixin, HypermediaMixin, View):
    affordance = Affordance("Widgets")

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("widgets")


class WidgetUndeclared(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("nothing declared")


def widget_detail(request: HttpRequest, pk: int) -> HttpResponse:
    return HttpResponse(f"widget {pk}")


@login_required
@affordance(
    label="Renew",
    rel=("edit",),
    permission="tests.change_widget",
    model=Widget,
    unavailable=lambda request, widget: retired_reason(widget),
)
def widget_renew_fbv(request: HttpRequest, pk: int) -> HttpResponse:
    return HttpResponse("renewed")
