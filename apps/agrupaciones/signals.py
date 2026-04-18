from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ConfiguracionBot


@receiver(post_save, sender=ConfiguracionBot)
def trigger_rag_processing(sender, instance, created, **kwargs):
    """
    Dispara el procesamiento RAG en background solo cuando hay un documento
    y el campo fue marcado explícitamente para reprocesar (update_fields no
    excluye 'documento_conocimiento').

    Se usa django-q2 para no bloquear el request HTTP ni el guardado del admin.
    """
    update_fields = kwargs.get('update_fields')

    # Si el save fue parcial (update_fields) y no incluye documento_conocimiento,
    # no tiene sentido reindexar (ej: cuando services.py actualiza texto_extraido).
    if update_fields and 'documento_conocimiento' not in update_fields:
        return

    if not instance.documento_conocimiento:
        return

    from django_q.tasks import async_task
    async_task('apps.agrupaciones.services.process_pdf_rag', instance)
