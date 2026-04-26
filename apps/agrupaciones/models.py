import uuid
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

def validate_file_size(value):
    if value.size > 5 * 1024 * 1024:
        raise ValidationError("El archivo máximo permitido es 5MB.")

class Agrupacion(models.Model):
    # UUID para Deep Linking de Telegram
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=200)
    
    def __str__(self):
        return self.nombre

class SolicitudBot(models.Model):
    agrupacion = models.ForeignKey(Agrupacion, on_delete=models.CASCADE)
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    aprobado = models.BooleanField(default=False)

class ConfiguracionBot(models.Model):
    TONOS = (('amigable', 'Amigable'), ('formal', 'Formal'), ('tecnico', 'Técnico'))
    agrupacion = models.OneToOneField(Agrupacion, on_delete=models.CASCADE)
    nombre_bot = models.CharField(max_length=100, default="Asistente UNIBot")
    tono = models.CharField(max_length=20, choices=TONOS, default='amigable')
    # Se subirá a Supabase Storage gracias a django-storages
    documento_conocimiento = models.FileField(upload_to='pdfs/', validators=[validate_file_size], null=True, blank=True)
    texto_extraido = models.TextField(blank=True)
    correo_remitente = models.EmailField(blank=True, default="")
    clave_app_remitente = models.CharField(max_length=255, blank=True, default="")
    google_email = models.EmailField(blank=True, default="")
    google_refresh_token = models.TextField(blank=True, default="")
    google_connected_at = models.DateTimeField(null=True, blank=True)
    notion_access_token = models.TextField(blank=True, default="")
    notion_workspace_id = models.CharField(max_length=255, blank=True, default="")
    notion_workspace_name = models.CharField(max_length=255, blank=True, default="")
    notion_connected_at = models.DateTimeField(null=True, blank=True)
    google_calendar_enabled = models.BooleanField(default=False)
    google_calendar_id = models.CharField(max_length=255, blank=True, default="")
    clipup_enabled = models.BooleanField(default=False)
    clipup_api_token = models.TextField(blank=True, default="")
    clipup_list_id = models.CharField(max_length=100, blank=True, default="")
    clipup_connected_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Bot de {self.agrupacion.nombre}"