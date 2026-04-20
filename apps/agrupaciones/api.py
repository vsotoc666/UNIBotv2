from typing import List
from ninja import Router, Form, File, Schema
from ninja.files import UploadedFile
from .models import ConfiguracionBot, Agrupacion, DocumentoConocimiento
from ninja.errors import HttpError
import traceback

router = Router()

class DocumentoOut(Schema):
    id: int
    nombre: str
    fecha_subida: str
    procesado: bool

@router.get("/documentos/", response=List[DocumentoOut])
def listar_documentos(request):
    try:
        agrupacion = Agrupacion.objects.get(user=request.user)
        docs = DocumentoConocimiento.objects.filter(agrupacion=agrupacion).order_by('-fecha_subida')
        return [{
            "id": d.id,
            "nombre": d.nombre,
            "fecha_subida": d.fecha_subida.strftime("%Y-%m-%d %H:%M"),
            "procesado": d.procesado
        } for d in docs]
    except Exception as e:
        raise HttpError(400, str(e))

@router.post("/documentos/subir/")
def subir_documento(request, archivo: UploadedFile = File(...)):
    try:
        agrupacion = Agrupacion.objects.get(user=request.user)
        # Crear el registro del documento (esto dispara el signal para procesar RAG)
        doc = DocumentoConocimiento.objects.create(
            agrupacion=agrupacion,
            archivo=archivo,
            nombre=archivo.name
        )
        return {"status": "success", "message": f"Archivo '{doc.nombre}' subiendo y procesando..."}
    except Exception as e:
        traceback.print_exc()
        raise HttpError(400, str(e))

@router.delete("/documentos/{doc_id}/")
def borrar_documento(request, doc_id: int):
    try:
        agrupacion = Agrupacion.objects.get(user=request.user)
        doc = DocumentoConocimiento.objects.get(id=doc_id, agrupacion=agrupacion)
        doc.delete() # Esto también borra los fragmentos asociados vía CASCADE
        return {"status": "success", "message": "Documento eliminado"}
    except Exception as e:
        raise HttpError(400, "No se pudo eliminar el documento")

@router.post("/bot-config/")
def configurar_bot(request, nombre_bot: str = Form(...), tono: str = Form(...)):
    try:
        agrupacion = Agrupacion.objects.get(user=request.user)
        config, _ = ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)
        
        config.nombre_bot = nombre_bot
        config.tono = tono
        config.save()
            
        return {"status": "success", "message": "Configuración del bot actualizada"}
        
    except Exception as e:
        traceback.print_exc()
        raise HttpError(400, str(e))