from django.apps import AppConfig

class AgrupacionesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.agrupaciones'

    def ready(self):
        import apps.agrupaciones.signals
