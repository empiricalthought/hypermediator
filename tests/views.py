"""Test-only views declaring affordances."""

import uuid
from types import MappingProxyType

from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.forms import modelform_factory
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import redirect
from django.views import View
from django.views.generic.detail import DetailView, SingleObjectMixin
from django.views.generic.edit import CreateView, DeleteView, FormView, UpdateView

from hypermediator.affordances import Affordance, Placement
from hypermediator.concurrency import ConcurrencyMixin
from hypermediator.shortcuts import render
from hypermediator.views import HypermediaMixin, affordance
from tests.models import Gadget, Thing, Widget


def retired_reason(widget: Widget | None) -> str | None:
    return "Retired widgets cannot be renewed" if widget and widget.status == "retired" else None


class RenewPost(View):
    def post(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponseBase:
        return HttpResponse("renewed")


class WidgetRenew(PermissionRequiredMixin, HypermediaMixin, SingleObjectMixin, RenewPost):  # type: ignore[type-arg]
    model = Widget
    permission_required = "tests.change_widget"
    raise_exception = True
    affordance = Affordance("Renew", rel=("edit",), link_header=True)

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
    link_header=True,
    permission="tests.change_widget",
    model=Widget,
    unavailable=lambda request, widget: retired_reason(widget),
)
def widget_renew_fbv(request: HttpRequest, pk: int) -> HttpResponse:
    return HttpResponse("renewed")


class WidgetCreate(HypermediaMixin, CreateView):  # type: ignore[type-arg]
    http_method_names = ["get", "post", "head", "options"]  # noqa: RUF012
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


class PipelineCbvStrict(PipelineCbv):
    http_method_names = ["get", "post", "head", "options"]  # noqa: RUF012


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


class WidgetNext(HypermediaMixin, View):
    affordance = Affordance(
        "Next", rel=("next", "edit", "https://example.com/rel/x"), link_header=True
    )

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("next")


class WidgetQuiet(HypermediaMixin, View):
    """Has a rel but is not selected for the Link header."""

    affordance = Affordance("Quiet", rel=("help",))

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("quiet")


OVERRIDE = Placement(target="#panel", swap="innerHTML", select="#panel")


class WidgetPage(HypermediaMixin, View):
    placements = MappingProxyType({"widget-renew": OVERRIDE})
    link_headers = MappingProxyType({"widget-renew": False, "widget-quiet": True})

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("page")


@affordance(
    label="Page fn",
    placements={"widget-renew": OVERRIDE},
    link_headers={"widget-renew": False, "widget-quiet": True},
)
def widget_page_fbv(request: HttpRequest) -> HttpResponse:
    return HttpResponse("page")


class RenewForm(forms.Form):
    renewal_date = forms.DateField()


class RenewFormView(HypermediaMixin, FormView):  # type: ignore[type-arg]
    http_method_names = ["get", "post", "head", "options"]  # noqa: RUF012
    form_class = RenewForm
    template_name = "tags/renew.html"
    success_url = "/widgets/"
    affordance = Affordance("Renew book")


ODD = "<b>\"&'"


class WidgetOdd(HypermediaMixin, View):
    affordance = Affordance(ODD)

    def unavailable(self, obj: object | None) -> str | None:
        return ODD

    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse("odd")


class WidgetEdit(ConcurrencyMixin, HypermediaMixin, UpdateView):  # type: ignore[type-arg]
    http_method_names = ["get", "post", "head", "options"]  # noqa: RUF012
    model = Widget
    fields = ("name",)
    template_name = "concurrency/form.html"
    success_url = "/widgets/"
    affordance = Affordance("Edit widget")

    def unavailable(self, obj: object | None) -> str | None:
        return retired_reason(obj) if isinstance(obj, Widget) else None


class WidgetEditAll(ConcurrencyMixin, HypermediaMixin, UpdateView):  # type: ignore[type-arg]
    """A ``__all__``-style form that excludes ``status``."""

    http_method_names = ["get", "post", "head", "options"]  # noqa: RUF012

    model = Widget
    form_class = modelform_factory(Widget, exclude=["status"])
    template_name = "concurrency/form.html"
    success_url = "/widgets/"
    affordance = Affordance("Edit widget fully")


class ThingEdit(ConcurrencyMixin, HypermediaMixin, UpdateView):  # type: ignore[type-arg]
    http_method_names = ["get", "post", "head", "options"]  # noqa: RUF012
    model = Thing
    fields = ("when", "stamp", "price", "owner", "tags", "note")
    template_name = "concurrency/thing_form.html"
    success_url = "/widgets/"
    affordance = Affordance("Edit thing")


def mutating_get(request: HttpRequest) -> HttpResponse:
    """A GET that wrongly changes state, for the state-safety assertion."""
    Widget.objects.create(name="created by GET")
    return HttpResponse("mutated")


def saving_get(request: HttpRequest) -> HttpResponse:
    """A GET that wrongly re-saves an existing row: an UPDATE, with no new row or pk."""
    widget = Widget.objects.get()
    widget.name = "renamed by GET"
    widget.save()
    return HttpResponse("saved")


class WidgetRenewBySlug(HypermediaMixin, SingleObjectMixin, RenewPost):  # type: ignore[type-arg]
    """Routed by slug, not pk: the URL kwargs come from the route."""

    model = Widget
    slug_field = "name"
    affordance = Affordance("Renew by name")

    def unavailable(self, obj: object | None) -> str | None:
        return retired_reason(obj) if isinstance(obj, Widget) else None


@affordance(label="Rename by name", url_kwargs=lambda widget: {"name": widget.name})
def widget_rename_fbv(request: HttpRequest, name: str) -> HttpResponse:
    return HttpResponse("renamed")


@affordance(label="Guarded", permission="tests.change_widget")
def widget_guarded_fbv(request: HttpRequest) -> HttpResponse:
    return HttpResponse("guarded")


class WidgetLoginPost(HypermediaMixin, LoginRequiredMixin, View):
    """The auth mixin sits inside HypermediaMixin, so its login redirect passes through it."""

    affordance = Affordance("Archive")

    def post(self, request: HttpRequest) -> HttpResponseBase:
        return redirect("/widgets/")
