from django.db import models
import uuid
from apps.agrupaciones.models import Agrupacion
from django.db.models.signals import post_save
from django.dispatch import receiver

class Evento(models.Model):
    TIPO_INSCRIPCION_CHOICES = [
        ("interno", "Formulario interno UNIBot"),
        ("google_form", "Google Form externo"),
    ]

    agrupacion = models.ForeignKey(Agrupacion, on_delete=models.CASCADE)
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField()
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    tipo_inscripcion = models.CharField(
        max_length=20,
        choices=TIPO_INSCRIPCION_CHOICES,
        default="interno",
    )
    form_externo_url = models.URLField(blank=True, default="")
    sheet_respuestas_url = models.URLField(blank=True, default="")
    campo_correo_label = models.CharField(max_length=120, blank=True, default="")
    campo_nombre_label = models.CharField(max_length=120, blank=True, default="")
    enviar_confirmacion_email = models.BooleanField(default=False)
    cerrado = models.BooleanField(default=False)
    cerrado_en = models.DateTimeField(null=True, blank=True)
    acta_notion_url = models.URLField(blank=True, default="")

    def __str__(self):
        return self.titulo

class FormularioRegistro(models.Model):
    evento = models.OneToOneField(Evento, on_delete=models.CASCADE)
    slug = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    
    def __str__(self):
        return f"Formulario - {self.evento.titulo}"

class Inscripcion(models.Model):
    formulario = models.ForeignKey(FormularioRegistro, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=100)
    correo = models.EmailField()
    telefono = models.CharField(max_length=20)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    asistio = models.BooleanField(default=False)
    asistencia_marcada_en = models.DateTimeField(null=True, blank=True)
    datos_extra = models.JSONField(default=dict, blank=True)
    confirmacion_email_enviada = models.BooleanField(default=False)
    confirmacion_email_enviada_en = models.DateTimeField(null=True, blank=True)
    recordatorio_24h_enviado_en = models.DateTimeField(null=True, blank=True)
    recordatorio_2h_enviado_en = models.DateTimeField(null=True, blank=True)
    certificado_archivo = models.FileField(upload_to="certificados/", null=True, blank=True)
    certificado_enviado_en = models.DateTimeField(null=True, blank=True)

# Signal para crear automáticamente el formulario al crear un evento
@receiver(post_save, sender=Evento)
def crear_formulario_evento(sender, instance, created, **kwargs):
    if created:
        FormularioRegistro.objects.create(evento=instance)