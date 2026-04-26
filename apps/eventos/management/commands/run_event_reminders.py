from django.core.management.base import BaseCommand

from apps.eventos.automation import ejecutar_recordatorios_eventos


class Command(BaseCommand):
    help = "Envía recordatorios 24h/2h de eventos próximos."

    def handle(self, *args, **options):
        result = ejecutar_recordatorios_eventos()
        self.stdout.write(
            self.style.SUCCESS(
                f"Recordatorios enviados -> 24h: {result['recordatorios_24h_enviados']} | 2h: {result['recordatorios_2h_enviados']}"
            )
        )
