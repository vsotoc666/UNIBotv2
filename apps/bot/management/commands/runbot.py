from django.core.management.base import BaseCommand
from apps.bot.telegram_bot import main

class Command(BaseCommand):
    help = 'Inicia el bot de Telegram de UNIBot'

    def handle(self, *args, **options):
        import sys
        if sys.platform == 'win32':
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(main())
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('\nBot detenido correctamente.'))