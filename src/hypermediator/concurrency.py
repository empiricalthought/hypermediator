"""Form-level optimistic concurrency: a fingerprint of the fields a form exposes, carried in a
hidden field and compared with the stored values on submit. No ETag is emitted and ``If-Match``
is ignored."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from django import forms
from django.db import transaction
from django.db.models import Model
from django.forms.models import model_to_dict
from django.forms.utils import ErrorDict
from django.http import HttpRequest, HttpResponse

FINGERPRINT_FIELD = "_hm_fingerprint"


def stored_values(instance: Model, fields: Iterable[str]) -> dict[str, Any]:
    """The form-prepared values of ``fields``: a many-to-many as the sorted list of related pks,
    so neither related objects' text nor their query order can change the result."""
    values = model_to_dict(instance, list(fields))
    return {
        name: sorted((o.pk for o in value), key=str)
        if isinstance(value, list)
        else value.pk
        if isinstance(value, Model)
        else value
        for name, value in values.items()
    }


def fingerprint(instance: Model, fields: Iterable[str]) -> str:
    """A SHA-256 hex digest of ``instance``'s values for ``fields``."""
    values = stored_values(instance, fields)
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


class ConcurrencyMixin:
    """For an ``UpdateView``, placed before ``HypermediaMixin``. A submit whose fingerprint no
    longer matches the stored object gets a 409 with the form re-rendered against the current
    values; a missing or garbled fingerprint counts as stale."""

    def get_form(self, form_class: Any = None) -> Any:
        form = super().get_form(form_class)  # type: ignore[misc]
        return self._with_fingerprint(form, fingerprint(self.object, self._fields()))

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        # One transaction holds a row lock from the fresh fetch (made before the form binds,
        # as validation mutates the form's instance) through the check and the save.
        with transaction.atomic():
            self.object = self.get_object(self.get_queryset().select_for_update())  # type: ignore[attr-defined]
            fields = self._fields()
            stored = fingerprint(self.object, fields)
            if request.POST.get(FINGERPRINT_FIELD) != stored:
                return self._conflict(request, stored, fields)
            response: HttpResponse = super().post(request, *args, **kwargs)  # type: ignore[misc]
            return response

    def _fields(self) -> list[str]:
        """The model fields the form exposes, honouring ``fields`` and ``exclude``."""
        model_fields = {f.name for f in self.object._meta.get_fields() if f.editable}
        base_fields = self.get_form_class().base_fields  # type: ignore[attr-defined]
        return [n for n in base_fields if n in model_fields and n != FINGERPRINT_FIELD]

    @staticmethod
    def _with_fingerprint(form: forms.BaseForm, value: str) -> forms.BaseForm:
        form.fields[FINGERPRINT_FIELD] = forms.CharField(
            widget=forms.HiddenInput, required=False, initial=value
        )
        return form

    def _conflict(self, request: HttpRequest, stored: str, fields: list[str]) -> HttpResponse:
        current = stored_values(self.object, fields)
        data = request.POST.copy()
        data[FINGERPRINT_FIELD] = stored
        kwargs = self.get_form_kwargs()  # type: ignore[attr-defined]
        kwargs.update(data=data, instance=self.get_object())  # type: ignore[attr-defined]
        form = self._with_fingerprint(self.get_form_class()(**kwargs), stored)  # type: ignore[attr-defined]
        # Only the conflict is reported, not the field errors the stale values may also have.
        form.full_clean()
        form._errors = ErrorDict()  # type: ignore[attr-defined]
        verbose_name = self.object._meta.verbose_name
        form.add_error(
            None,
            f"This {verbose_name} was changed by someone else since you opened the form. "
            "Review the current values and submit again.",
        )
        context = self.get_context_data(form=form, hm_current=current)  # type: ignore[attr-defined]
        response: HttpResponse = self.render_to_response(context, status=409)  # type: ignore[attr-defined]
        return response
