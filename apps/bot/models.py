from django.db import models

class TelegramChat(models.Model):
    """
    Asocia un usuario de Telegram con una agrupación específica mediante Deep Linking.
    """
    chat_id = models.CharField(max_length=100, unique=True)
    agrupacion = models.ForeignKey('agrupaciones.Agrupacion', on_delete=models.CASCADE, related_name='telegram_chats')
    fecha_asociacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Chat {self.chat_id} -> {self.agrupacion.nombre}"