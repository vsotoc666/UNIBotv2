from __future__ import annotations

import urllib.error
import urllib.request
import json
from datetime import timedelta
from typing import Optional

from django.core.files.base import ContentFile
from django.utils import timezone

from apps.agrupaciones.models import ConfiguracionBot
from apps.eventos.clipup import crear_tarea_clipup_desde_inscripcion
from apps.eventos.emails import enviar_confirmacion_inscripcion, enviar_correo_evento
from apps.eventos.models import Evento, Inscripcion
from apps.eventos.notion import crear_acta_evento_notion, crear_item_inscripcion_notion


def _inscripcion_cancelada(inscripcion: Inscripcion) -> bool:
    extras = inscripcion.datos_extra or {}
    raw = str(extras.get("cancelado") or extras.get("cancelada") or "").strip().lower()
    return raw in {"1", "true", "si", "sí", "yes"}


def _prioridad_por_evento(evento: Evento) -> str:
    if evento.tipo_inscripcion == "google_form":
        return "media"
    return "alta"


def _es_recurrente(inscripcion: Inscripcion) -> bool:
    return (
        Inscripcion.objects.filter(
            formulario__evento__agrupacion=inscripcion.formulario.evento.agrupacion,
            correo__iexact=inscripcion.correo,
        )
        .exclude(pk=inscripcion.pk)
        .exists()
    )


def ejecutar_flujo_post_inscripcion(inscripcion: Inscripcion) -> dict:
    evento = inscripcion.formulario.evento
    config = ConfiguracionBot.objects.filter(agrupacion=evento.agrupacion).first()
    prioridad = _prioridad_por_evento(evento)

    mail_ok = enviar_confirmacion_inscripcion(inscripcion)
    clipup_ok = crear_tarea_clipup_desde_inscripcion(inscripcion)
    notion_url = ""
    if config and config.notion_access_token:
        notion_url = crear_item_inscripcion_notion(
            config=config,
            evento_titulo=evento.titulo,
            nombre=inscripcion.nombre,
            correo=inscripcion.correo,
            telefono=inscripcion.telefono,
            prioridad=prioridad,
        )

    extras = dict(inscripcion.datos_extra or {})
    extras["prioridad"] = prioridad
    if notion_url:
        extras["notion_url"] = notion_url
    inscripcion.datos_extra = extras
    inscripcion.save(update_fields=["datos_extra"])
    return {
        "mail_ok": mail_ok,
        "clipup_ok": clipup_ok,
        "notion_url": notion_url,
        "prioridad": prioridad,
    }


def _pdf_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def generar_certificado_pdf_bytes(inscripcion: Inscripcion) -> bytes:
    evento = inscripcion.formulario.evento
    lines = [
        "CERTIFICADO DE ASISTENCIA",
        "",
        f"Se certifica que: {inscripcion.nombre}",
        f"Correo: {inscripcion.correo}",
        "",
        "Participó en el evento:",
        evento.titulo,
        "",
        f"Fecha inicio: {timezone.localtime(evento.fecha_inicio):%Y-%m-%d %H:%M}",
        f"Fecha fin: {timezone.localtime(evento.fecha_fin):%Y-%m-%d %H:%M}",
        "",
        "UNIBot",
    ]

    stream_lines = ["BT", "/F1 14 Tf", "60 760 Td"]
    leading = 20
    first = True
    for row in lines:
        escaped = _pdf_escape(row)
        if first:
            stream_lines.append(f"({escaped}) Tj")
            first = False
        else:
            stream_lines.append(f"0 -{leading} Td")
            stream_lines.append(f"({escaped}) Tj")
    stream_lines.append("ET")
    content = "\n".join(stream_lines).encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj")
    objects.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj"
    )
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj")
    objects.append(
        f"5 0 obj << /Length {len(content)} >> stream\n".encode("latin-1")
        + content
        + b"\nendstream endobj"
    )

    chunks = [b"%PDF-1.4\n"]
    offsets = [0]
    for obj in objects:
        offsets.append(sum(len(c) for c in chunks))
        chunks.append(obj + b"\n")
    xref_start = sum(len(c) for c in chunks)
    chunks.append(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    chunks.append(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        chunks.append(f"{off:010d} 00000 n \n".encode("latin-1"))
    chunks.append(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode(
            "latin-1"
        )
    )
    return b"".join(chunks)


def enviar_certificado_si_asistio(inscripcion: Inscripcion) -> bool:
    if not inscripcion.asistio or not inscripcion.correo:
        return False
    if inscripcion.certificado_enviado_en:
        return True

    evento = inscripcion.formulario.evento
    pdf_bytes = generar_certificado_pdf_bytes(inscripcion)
    filename = f"certificado_{inscripcion.id}.pdf"
    if not inscripcion.certificado_archivo:
        inscripcion.certificado_archivo.save(filename, ContentFile(pdf_bytes), save=False)
    subject = f"Certificado de asistencia - {evento.titulo}"
    message = (
        f"Hola {inscripcion.nombre},\n\n"
        "Adjuntamos tu certificado de asistencia.\n"
        f"Evento: {evento.titulo}\n\n"
        "Gracias por participar."
    )
    sent = enviar_correo_evento(
        evento=evento,
        to_email=inscripcion.correo,
        subject=subject,
        message=message,
        attachment_name=filename,
        attachment_bytes=pdf_bytes,
    )
    if not sent:
        return False

    inscripcion.certificado_enviado_en = timezone.now()
    inscripcion.save(update_fields=["certificado_archivo", "certificado_enviado_en"])

    config = ConfiguracionBot.objects.filter(agrupacion=evento.agrupacion).first()
    if config and config.notion_access_token:
        cert_url = ""
        try:
            cert_url = inscripcion.certificado_archivo.url
        except Exception:
            cert_url = ""
        notion_url = crear_item_inscripcion_notion(
            config=config,
            evento_titulo=evento.titulo,
            nombre=inscripcion.nombre,
            correo=inscripcion.correo,
            telefono=inscripcion.telefono,
            prioridad=_prioridad_por_evento(evento),
        )
        extras = dict(inscripcion.datos_extra or {})
        if cert_url:
            extras["certificado_url"] = cert_url
        if notion_url:
            extras["notion_certificado_url"] = notion_url
        inscripcion.datos_extra = extras
        inscripcion.save(update_fields=["datos_extra"])
    return True


def _cargar_tareas_pendientes_clipup(config: Optional[ConfiguracionBot]) -> list[str]:
    if not config:
        return []
    token = (config.clipup_api_token or "").replace("Bearer ", "").strip()
    list_id = (config.clipup_list_id or "").strip()
    if not token or not list_id:
        return []
    url = f"https://api.clickup.com/api/v2/list/{list_id}/task?statuses[]=to%20do&statuses[]=in%20progress"
    req = urllib.request.Request(url, headers={"Authorization": token}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    tareas = []
    for row in data.get("tasks") or []:
        name = (row.get("name") or "").strip()
        if name:
            tareas.append(name)
    return tareas[:15]


def cerrar_evento_y_generar_acta(evento: Evento, comentarios: str = "") -> dict:
    inscritos_qs = Inscripcion.objects.filter(formulario__evento=evento)
    inscritos = inscritos_qs.count()
    presentes = inscritos_qs.filter(asistio=True).count()
    porcentaje = (presentes * 100.0 / inscritos) if inscritos else 0.0

    config = ConfiguracionBot.objects.filter(agrupacion=evento.agrupacion).first()
    tareas = _cargar_tareas_pendientes_clipup(config)
    notion_url = ""
    if config and config.notion_access_token:
        notion_url = crear_acta_evento_notion(
            config=config,
            evento_titulo=evento.titulo,
            inscritos=inscritos,
            presentes=presentes,
            porcentaje_asistencia=porcentaje,
            comentarios=comentarios,
            tareas_pendientes=tareas,
        )
    evento.cerrado = True
    evento.cerrado_en = timezone.now()
    if notion_url:
        evento.acta_notion_url = notion_url
    evento.save(update_fields=["cerrado", "cerrado_en", "acta_notion_url"])
    return {
        "inscritos": inscritos,
        "presentes": presentes,
        "porcentaje_asistencia": round(porcentaje, 2),
        "tareas_pendientes": tareas,
        "acta_notion_url": notion_url,
    }


def ejecutar_recordatorios_eventos(agrupacion_id: Optional[int] = None) -> dict:
    now = timezone.now()
    horizon_24 = now + timedelta(hours=24, minutes=30)
    horizon_2 = now + timedelta(hours=2, minutes=20)
    events_qs = Evento.objects.filter(fecha_inicio__gt=now, cerrado=False)
    if agrupacion_id:
        events_qs = events_qs.filter(agrupacion_id=agrupacion_id)

    sent_24h = 0
    sent_2h = 0
    for evento in events_qs:
        inscritos = Inscripcion.objects.filter(formulario__evento=evento)
        for ins in inscritos:
            if _inscripcion_cancelada(ins):
                continue
            recurrente = _es_recurrente(ins)
            nombre_tipo = "recurrente" if recurrente else "primera vez"
            delta = evento.fecha_inicio - now
            if delta <= timedelta(hours=24, minutes=30) and delta > timedelta(hours=2, minutes=30):
                if ins.recordatorio_24h_enviado_en:
                    continue
                ok = enviar_correo_evento(
                    evento=evento,
                    to_email=ins.correo,
                    subject=f"Recordatorio 24h - {evento.titulo}",
                    message=(
                        f"Hola {ins.nombre},\n\n"
                        f"Tu evento '{evento.titulo}' inicia en menos de 24 horas.\n"
                        f"Tipo de participante: {nombre_tipo}.\n"
                        "Te esperamos."
                    ),
                )
                if ok:
                    ins.recordatorio_24h_enviado_en = timezone.now()
                    ins.save(update_fields=["recordatorio_24h_enviado_en"])
                    sent_24h += 1
            elif delta <= timedelta(hours=2, minutes=20) and delta > timedelta(minutes=30):
                if ins.recordatorio_2h_enviado_en:
                    continue
                ok = enviar_correo_evento(
                    evento=evento,
                    to_email=ins.correo,
                    subject=f"Recordatorio 2h - {evento.titulo}",
                    message=(
                        f"Hola {ins.nombre},\n\n"
                        f"Tu evento '{evento.titulo}' inicia en menos de 2 horas.\n"
                        f"Tipo de participante: {nombre_tipo}.\n"
                        "Nos vemos pronto."
                    ),
                )
                if ok:
                    ins.recordatorio_2h_enviado_en = timezone.now()
                    ins.save(update_fields=["recordatorio_2h_enviado_en"])
                    sent_2h += 1

    return {"recordatorios_24h_enviados": sent_24h, "recordatorios_2h_enviados": sent_2h}
