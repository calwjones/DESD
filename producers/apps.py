from django.apps import AppConfig


class ProducersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'producers'

    def ready(self):
        import producers.signals  # noqa: F401
