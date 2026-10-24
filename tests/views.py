"""Test-only views declaring affordances."""

import uuid

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import redirect
from django.views import View
from django.views.generic.detail import DetailView, SingleObjectMixin
from django.views.generic.edit import CreateView, DeleteView, FormView, UpdateView

from hypermediator.affordances import Affordance
from hypermediator.shortcuts import render
from hypermediator.views import HypermediaMixin, affordance
from tests.models import Gadget, Widget


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


class WidgetCreate(HypermediaMixin, CreateView):  # type: ignore[type-arg]
    model = Widget
    fields = ("name",)
    affordance = Affordance("New widget")

    def unavailable(self, obj: object | None) -> str | None:
        return "Creation is closed" if Widget.objects.filter(status="full").exists() else None


class WidgetUpdate(HypermediaMixin, UpdateView):  # type: ignore[type-arg]
    model = Widget
    fields = ("name",)
    affordance = Affordance("Rename")

    def unavailable(self, obj: object | None) -> str | None:
        return retired_reason(obj) if isinstance(obj, Widget) else None


class WidgetDelete(HypermediaMixin, DeleteView):  # type: ignore[type-arg]
    model = Widget
    success_url = "/widgets/"
    affordance = Affordance("Delete")

    def unavailable(self, obj: object | None) -> str | None:
        return retired_reason(obj) if isinstance(obj, Widget) else None


class WidgetDetailView(HypermediaMixin, DetailView):  # type: ignore[type-arg]
    model = Widget
    affordance = Affordance("View")


class PlainDetailView(DetailView):  # type: ignore[type-arg]
    model = Widget


@affordance(
    label="Renew gadget",
    model=Gadget,
    unavailable=lambda request, gadget: "Retired" if gadget.status == "retired" else None,
)
def gadget_renew(request: HttpRequest, pk: uuid.UUID) -> HttpResponse:
    return HttpResponse("renewed")


class PipelineForm(forms.Form):
    name = forms.CharField()


class PipelineCbv(HypermediaMixin, FormView):  # type: ignore[type-arg]
    form_class = PipelineForm
    template_name = "pipeline/form.html"
    partial = "body"
    success_url = "/widgets/"
    affordance = Affordance("Pipeline")


class PlainFormView(FormView):  # type: ignore[type-arg]
    form_class = PipelineForm
    template_name = "pipeline/form.html"
    success_url = "/widgets/"


@affordance(label="Pipeline fn", form_class=PipelineForm, partial="body")
def pipeline_fbv(request: HttpRequest) -> HttpResponse:
    form = PipelineForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        return redirect("/widgets/")
    return render(request, "pipeline/form.html", {"form": form}, partial="body")
