from ninja import Router, Schema
from typing import List, Optional
from datetime import datetime
from .models import Evento
from apps.agrupaciones.models import Agrupacion

router = Router()

# 1. ESQUEMA DE VALIDACIÓN (Obliga a Ninja a leer el Body (JSON) y no la URL)
class EventoIn(Schema):
    titulo: str
    descripcion: str
    fecha_inicio: datetime
    fecha_fin: datetime

@router.get("/dashboard-data/")
def get_dashboard_data(request):
    eventos = Evento.objects.filter(agrupacion__user=request.user).select_related('formularioregistro').order_by('fecha_inicio')
    data = []
    for e in eventos:
        data.append({
            "id": e.id,
            "title": e.titulo,
            "start": e.fecha_inicio.isoformat(),
            "end": e.fecha_fin.isoformat(),
            "descripcion": e.descripcion,
            "slug": str(e.formularioregistro.slug) if hasattr(e, 'formularioregistro') else None,
            "backgroundColor": "#0A1929",
            "borderColor": "#0A1929"
        })
    return data

@router.post("/")
def crear_evento(request, payload: EventoIn): # 2. APLICAMOS EL ESQUEMA AQUÍ
    agrupacion = Agrupacion.objects.get(user=request.user)
    
    # 3. Guardamos usando los atributos validados por Pydantic
    evento = Evento.objects.create(
        agrupacion=agrupacion,
        titulo=payload.titulo,
        descripcion=payload.descripcion,
        fecha_inicio=payload.fecha_inicio,
        fecha_fin=payload.fecha_fin
    )
    return {"status": "success", "id": evento.id}