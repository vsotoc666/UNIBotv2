from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import DocumentoConocimiento

@receiver(post_save, sender=DocumentoConocimiento)
def trigger_rag_processing(sender, instance, created, **kwargs):
    """
    Dispara el procesamiento RAG en background cuando se sube un nuevo documento.
    """
    # Si se acaba de crear o si el archivo cambió (aunque aquí simplificamos a 'siempre que no esté procesado')
    if not instance.procesado:
        from django_q.tasks import async_task
        async_task('apps.agrupaciones.services.process_pdf_rag', instance)
