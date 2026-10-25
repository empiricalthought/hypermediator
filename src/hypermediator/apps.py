from django.apps import AppConfig


class HypermediatorConfig(AppConfig):
    name = "hypermediator"
    verbose_name = "Hypermediator"

    def ready(self) -> None:
        from hypermediator import checks  # noqa: F401  (registers the system checks)
