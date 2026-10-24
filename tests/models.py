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
