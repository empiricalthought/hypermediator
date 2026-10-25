import uuid

from django.db import models
from django.urls import reverse


class Widget(models.Model):
    name = models.CharField(max_length=50)
    status = models.CharField(max_length=20, default="a")

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("widget-detail", kwargs={"pk": self.pk})


class Gadget(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=20, default="a")

    def __str__(self) -> str:
        return str(self.id)


class Thing(models.Model):
    """Every value type whose fingerprint must be stable across a render and a round-trip."""

    when = models.DateField()
    stamp = models.DateTimeField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    owner = models.ForeignKey(
        Widget, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    tags = models.ManyToManyField(Widget, blank=True, related_name="+")
    note = models.CharField(max_length=20, null=True, blank=True)  # noqa: DJ001

    def __str__(self) -> str:
        return f"Thing {self.pk}"
