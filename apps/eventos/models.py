from django.db import models
import uuid
from apps.agrupaciones.models import Agrupacion
from django.db.models.signals import post_save
from django.dispatch import receiver

class Evento(models.Model):
    agrupacion = models.ForeignKey(Agrupacion, on_delete=models.CASCADE)
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField()
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()

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

# Signal para crear automáticamente el formulario al crear un evento
@receiver(post_save, sender=Evento)
def crear_formulario_evento(sender, instance, created, **kwargs):
    if created:
        FormularioRegistro.objects.create(evento=instance)