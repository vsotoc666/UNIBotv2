import csv
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

from apps.agrupaciones.models import Agrupacion, ConfiguracionBot
from apps.eventos.automation import (
    cerrar_evento_y_generar_acta,
    ejecutar_flujo_post_inscripcion,
    ejecutar_recordatorios_eventos,
    enviar_certificado_si_asistio,
)
from apps.eventos.emails import enviar_confirmacion_inscripcion
from .models import Evento, Inscripcion

router = Router()


def _refresh_google_access_token(refresh_token: str) -> str:
    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
    if not client_id or not client_secret or not refresh_token:
        return ""
    payload = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        token_data = json.loads(response.read().decode("utf-8"))
    return (token_data.get("access_token") or "").strip()


def _crear_evento_google_calendar(evento: Evento, config: ConfiguracionBot) -> bool:
    refresh_token = (config.google_refresh_token or "").strip()
    calendar_id = (config.google_calendar_id or config.google_email or "").strip()
    if not refresh_token or not calendar_id:
        return False, "Google no está conectado o falta calendar_id."

    start_dt = evento.fecha_inicio
    end_dt = evento.fecha_fin
    if timezone.is_naive(start_dt):
        start_dt = timezone.make_aware(start_dt, timezone.get_current_timezone())
    if timezone.is_naive(end_dt):
        end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())
    if end_dt <= start_dt:
        # Google Calendar rechaza rangos vacios o invertidos (timeRangeEmpty).
        end_dt = start_dt + timedelta(hours=1)

    access_token = _refresh_google_access_token(refresh_token)
    if not access_token:
        return False, "No se pudo refrescar el token de Google."

    body = json.dumps(
        {
            "summary": evento.titulo,
            "description": evento.descripcion,
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
        }
    ).encode("utf-8")
    encoded_calendar_id = urllib.parse.quote(calendar_id, safe="")
    req = urllib.request.Request(
        f"https://www.googleapis.com/calendar/v3/calendars/{encoded_calendar_id}/events",
        data=body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status_code = getattr(response, "status", None) or response.getcode()
        ok = int(status_code) in (200, 201)
        return ok, "" if ok else f"Google Calendar devolvió estado {status_code}."
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return False, f"HTTP {e.code} al crear evento en Google Calendar. {body[:300]}"
    except Exception as e:
        return False, f"Error inesperado en Google Calendar: {str(e)}"

# 1. ESQUEMA DE VALIDACIÓN (Obliga a Ninja a leer el Body (JSON) y no la URL)
class EventoIn(Schema):
    titulo: str
    descripcion: str
    fecha_inicio: datetime
    fecha_fin: datetime
    tipo_inscripcion: Optional[str] = "interno"
    form_externo_url: Optional[str] = ""
    sheet_respuestas_url: Optional[str] = ""
    enviar_confirmacion_email: Optional[bool] = False


class InscripcionConfigIn(Schema):
    tipo_inscripcion: str
    form_externo_url: Optional[str] = ""
    sheet_respuestas_url: Optional[str] = ""
    enviar_confirmacion_email: Optional[bool] = False


class AsistenciaIn(Schema):
    asistio: bool


class CerrarEventoIn(Schema):
    comentarios: Optional[str] = ""


class InscripcionOut(Schema):
    id: int
    nombre: str
    correo: str
    telefono: str
    fecha_registro: datetime
    asistio: bool
    asistencia_marcada_en: Optional[datetime] = None
    datos_extra: dict


def _normalize_label(value: str) -> str:
    raw = (value or "").strip().lower()
    # Hace matching robusto entre "correo electronico" y "correo electrónico".
    no_accents = "".join(
        ch for ch in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(ch)
    )
    return "".join(ch for ch in no_accents if ch.isalnum())


def _pick_key(headers, preferred_keys):
    normalized_map = {_normalize_label(h): h for h in headers}
    for preferred in preferred_keys:
        hit = normalized_map.get(_normalize_label(preferred))
        if hit:
            return hit
    return None


def _extract_google_form_id(form_url: str) -> str:
    raw = (form_url or "").strip()
    # Forms API usa el ID del enlace de edicion: /forms/d/{formId}/edit
    # El ID de enlaces publicos /forms/d/e/{publicId}/viewform no funciona en la API.
    hit = re.search(r"forms/d/([a-zA-Z0-9_-]+)", raw)
    if hit:
        return hit.group(1)
    return ""


def _form_answer_to_text(answer: dict) -> str:
    if not isinstance(answer, dict):
        return ""
    text_answers = ((answer.get("textAnswers") or {}).get("answers") or [])
    if text_answers:
        return ", ".join((row or {}).get("value", "") for row in text_answers if (row or {}).get("value", ""))
    choice_answers = ((answer.get("choiceAnswers") or {}).get("answers") or [])
    if choice_answers:
        return ", ".join(choice_answers)
    return ""


def _google_get_json(url: str, access_token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.loads(response.read().decode("utf-8"))


def _sync_evento_desde_google_forms(evento: Evento, config: ConfiguracionBot) -> tuple[int, str]:
    form_id = _extract_google_form_id(evento.form_externo_url)
    if not form_id:
        return 0, "Usa el link de edición del Form (/forms/d/.../edit), no el link público /d/e/.../viewform."
    refresh_token = (config.google_refresh_token or "").strip()
    if not refresh_token:
        return 0, "Conecta Google para sincronizar respuestas del formulario."
    access_token = _refresh_google_access_token(refresh_token)
    if not access_token:
        return 0, "No se pudo renovar el token de Google."

    try:
        form_meta = _google_get_json(
            f"https://forms.googleapis.com/v1/forms/{form_id}",
            access_token,
        )
    except urllib.error.HTTPError as e:
        return 0, f"No se pudo leer el formulario (HTTP {e.code}). Verifica permisos."
    except Exception:
        return 0, "No se pudo leer el formulario de Google."

    question_titles = {}
    for item in form_meta.get("items", []):
        q_item = item.get("questionItem") or {}
        question = q_item.get("question") or {}
        q_id = (question.get("questionId") or "").strip()
        title = (item.get("title") or "").strip()
        if q_id and title:
            question_titles[q_id] = title

    if not question_titles:
        return 0, "No se encontraron preguntas en el formulario."

    rows = []
    page_token = ""
    while True:
        query = urllib.parse.urlencode(
            {"pageSize": 500, **({"pageToken": page_token} if page_token else {})}
        )
        url = f"https://forms.googleapis.com/v1/forms/{form_id}/responses?{query}"
        try:
            data = _google_get_json(url, access_token)
        except urllib.error.HTTPError as e:
            return 0, f"No se pudieron leer respuestas del formulario (HTTP {e.code})."
        except Exception:
            return 0, "No se pudieron leer respuestas del formulario."

        for response in data.get("responses", []):
            answers = response.get("answers") or {}
            row = {}
            respondent_email = (response.get("respondentEmail") or "").strip()
            if respondent_email:
                # Fallback: cuando Forms recopila correo como metadato, no como pregunta.
                row["respondent_email"] = respondent_email
            for q_id, answer in answers.items():
                label = question_titles.get(q_id, q_id)
                value = _form_answer_to_text(answer)
                if value:
                    row[label] = value
            if row:
                rows.append(row)
        page_token = (data.get("nextPageToken") or "").strip()
        if not page_token:
            break

    if not rows:
        return 0, "No hay respuestas para sincronizar."

    all_headers = list({k for row in rows for k in row.keys()})
    email_key = _pick_key(
        all_headers,
        [
            "correo",
            "correo electronico",
            "correo electrónico",
            "email",
            "e-mail",
            "mail",
            "respondent_email",
            "respondentemail",
        ],
    )
    name_key = _pick_key(
        all_headers,
        ["nombre", "nombre completo", "nombrecompleto", "fullname", "apellidos y nombres"],
    )
    phone_key = _pick_key(
        all_headers,
        ["telefono", "teléfono", "celular", "movil", "nrocelular"],
    )
    if not email_key:
        return 0, "No se encontró una pregunta de correo en el Google Form."

    formulario = evento.formularioregistro
    imported = 0
    for row in rows:
        correo = (row.get(email_key) or "").strip().lower()
        if not correo:
            continue
        nombre = (row.get(name_key) or "").strip() if name_key else ""
        telefono = (row.get(phone_key) or "").strip() if phone_key else ""

        extras = {}
        for key, value in row.items():
            if key in {email_key, name_key, phone_key}:
                continue
            if (value or "").strip():
                extras[key] = value.strip()

        ins = (
            Inscripcion.objects.filter(formulario=formulario, correo__iexact=correo)
            .order_by("id")
            .first()
        )
        if ins:
            changed_fields = []
            if nombre and ins.nombre != nombre:
                ins.nombre = nombre
                changed_fields.append("nombre")
            if telefono and ins.telefono != telefono:
                ins.telefono = telefono
                changed_fields.append("telefono")
            if extras:
                merged = dict(ins.datos_extra or {})
                merged.update(extras)
                if merged != ins.datos_extra:
                    ins.datos_extra = merged
                    changed_fields.append("datos_extra")
            if changed_fields:
                ins.save(update_fields=changed_fields)
            if evento.enviar_confirmacion_email and not ins.confirmacion_email_enviada:
                enviar_confirmacion_inscripcion(ins)
        else:
            ins = Inscripcion.objects.create(
                formulario=formulario,
                nombre=nombre or correo.split("@")[0],
                correo=correo,
                telefono=telefono or "",
                datos_extra=extras,
            )
            ejecutar_flujo_post_inscripcion(ins)
        imported += 1

    evento.campo_correo_label = email_key
    evento.campo_nombre_label = name_key or ""
    evento.save(update_fields=["campo_correo_label", "campo_nombre_label"])
    return imported, "Sincronización completada desde Google Forms API."


def _extract_sheet_id(sheet_url: str) -> str:
    parts = [p for p in (sheet_url or "").split("/") if p]
    if "d" in parts:
        idx = parts.index("d")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def _sheet_csv_url(sheet_url: str) -> str:
    sheet_id = _extract_sheet_id(sheet_url)
    if not sheet_id:
        return ""
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"


def _sync_evento_desde_sheet(evento: Evento) -> tuple[int, str]:
    csv_url = _sheet_csv_url(evento.sheet_respuestas_url)
    if not csv_url:
        return 0, "El link de Google Sheet no es válido."

    try:
        with urllib.request.urlopen(csv_url, timeout=25) as response:
            content = response.read().decode("utf-8-sig", errors="replace")
    except urllib.error.URLError:
        return 0, "No se pudo leer el Sheet. Verifica permisos o enlace."

    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []
    if not headers:
        return 0, "El Sheet no tiene cabeceras."

    email_key = _pick_key(
        headers,
        [
            "correo",
            "correo electronico",
            "correo electrónico",
            "correoelectronico",
            "email",
            "e-mail",
            "mail",
        ],
    )
    name_key = _pick_key(
        headers,
        ["nombre", "nombrecompleto", "apellidosynombres", "fullname"],
    )
    phone_key = _pick_key(
        headers,
        ["telefono", "celular", "movil", "nrocelular"],
    )

    if not email_key:
        return 0, "No se encontró una columna de correo en el Sheet."

    formulario = evento.formularioregistro
    imported = 0

    for row in reader:
        correo = (row.get(email_key) or "").strip().lower()
        if not correo:
            continue

        nombre = (row.get(name_key) or "").strip() if name_key else ""
        telefono = (row.get(phone_key) or "").strip() if phone_key else ""

        extras = {}
        for key, value in row.items():
            if key in {email_key, name_key, phone_key}:
                continue
            if (value or "").strip():
                extras[key] = value.strip()

        ins = (
            Inscripcion.objects.filter(formulario=formulario, correo__iexact=correo)
            .order_by("id")
            .first()
        )
        if ins:
            changed_fields = []
            if nombre and ins.nombre != nombre:
                ins.nombre = nombre
                changed_fields.append("nombre")
            if telefono and ins.telefono != telefono:
                ins.telefono = telefono
                changed_fields.append("telefono")
            if extras:
                merged = dict(ins.datos_extra or {})
                merged.update(extras)
                if merged != ins.datos_extra:
                    ins.datos_extra = merged
                    changed_fields.append("datos_extra")
            if changed_fields:
                ins.save(update_fields=changed_fields)
            if evento.enviar_confirmacion_email and not ins.confirmacion_email_enviada:
                enviar_confirmacion_inscripcion(ins)
        else:
            ins = Inscripcion.objects.create(
                formulario=formulario,
                nombre=nombre or correo.split("@")[0],
                correo=correo,
                telefono=telefono or "",
                datos_extra=extras,
            )
            ejecutar_flujo_post_inscripcion(ins)
        imported += 1

    evento.campo_correo_label = email_key
    evento.campo_nombre_label = name_key or ""
    evento.save(update_fields=["campo_correo_label", "campo_nombre_label"])
    return imported, "Sincronización completada."

@router.get("/dashboard-data/")
def get_dashboard_data(request):
    eventos = Evento.objects.filter(agrupacion__user=request.user).select_related('formularioregistro').order_by('fecha_inicio')
    data = []
    for e in eventos:
        inscritos_count = Inscripcion.objects.filter(formulario__evento=e).count()
        presentes_count = Inscripcion.objects.filter(formulario__evento=e, asistio=True).count()
        data.append({
            "id": e.id,
            "title": e.titulo,
            "start": e.fecha_inicio.isoformat(),
            "end": e.fecha_fin.isoformat(),
            "descripcion": e.descripcion,
            "slug": str(e.formularioregistro.slug) if hasattr(e, 'formularioregistro') else None,
            "tipo_inscripcion": e.tipo_inscripcion,
            "form_externo_url": e.form_externo_url,
            "sheet_respuestas_url": e.sheet_respuestas_url,
            "enviar_confirmacion_email": e.enviar_confirmacion_email,
            "inscritos_count": inscritos_count,
            "presentes_count": presentes_count,
            "backgroundColor": "#0A1929",
            "borderColor": "#0A1929"
        })
    return data

@router.post("/")
def crear_evento(request, payload: EventoIn): # 2. APLICAMOS EL ESQUEMA AQUÍ
    agrupacion = Agrupacion.objects.get(user=request.user)
    tipo = (payload.tipo_inscripcion or "interno").strip()
    if tipo not in {"interno", "google_form"}:
        return {"status": "error", "message": "tipo_inscripcion inválido"}
    if tipo == "google_form" and not (payload.form_externo_url or "").strip():
        return {"status": "error", "message": "Debes agregar el link del Google Form."}
    if payload.fecha_fin <= payload.fecha_inicio:
        return {
            "status": "error",
            "message": "La fecha/hora de fin debe ser mayor que la de inicio.",
        }
    
    evento = Evento.objects.create(
        agrupacion=agrupacion,
        titulo=payload.titulo,
        descripcion=payload.descripcion,
        fecha_inicio=payload.fecha_inicio,
        fecha_fin=payload.fecha_fin,
        tipo_inscripcion=tipo,
        form_externo_url=payload.form_externo_url or "",
        sheet_respuestas_url=payload.sheet_respuestas_url or "",
        enviar_confirmacion_email=bool(payload.enviar_confirmacion_email),
    )

    google_calendar_synced = False
    google_calendar_error = ""
    config = ConfiguracionBot.objects.filter(agrupacion=agrupacion).first()
    if config and config.google_calendar_enabled:
        try:
            google_calendar_synced, google_calendar_error = _crear_evento_google_calendar(evento, config)
        except Exception as e:
            google_calendar_synced = False
            google_calendar_error = str(e)

    return {
        "status": "success",
        "id": evento.id,
        "google_calendar_synced": google_calendar_synced,
        "google_calendar_error": google_calendar_error,
    }


@router.post("/{evento_id}/inscripcion-config/")
def guardar_inscripcion_config(request, evento_id: int, payload: InscripcionConfigIn):
    agrupacion = Agrupacion.objects.get(user=request.user)
    evento = get_object_or_404(Evento, pk=evento_id, agrupacion=agrupacion)

    tipo = (payload.tipo_inscripcion or "interno").strip()
    if tipo not in {"interno", "google_form"}:
        return {"status": "error", "message": "tipo_inscripcion inválido"}

    confirmar = bool(payload.enviar_confirmacion_email)
    if tipo == "google_form" and not (payload.form_externo_url or "").strip():
        return {"status": "error", "message": "Debes agregar el link del Google Form."}
    evento.tipo_inscripcion = tipo
    evento.form_externo_url = (payload.form_externo_url or "").strip()
    evento.sheet_respuestas_url = (payload.sheet_respuestas_url or "").strip()
    evento.enviar_confirmacion_email = confirmar
    evento.save(
        update_fields=[
            "tipo_inscripcion",
            "form_externo_url",
            "sheet_respuestas_url",
            "enviar_confirmacion_email",
        ]
    )

    return {"status": "success", "id": evento.id}


@router.get("/{evento_id}/inscritos/")
def listar_inscritos(request, evento_id: int):
    agrupacion = Agrupacion.objects.get(user=request.user)
    evento = get_object_or_404(Evento, pk=evento_id, agrupacion=agrupacion)
    inscritos = (
        Inscripcion.objects.filter(formulario__evento=evento)
        .order_by("-fecha_registro")
    )
    return [
        InscripcionOut(
            id=row.id,
            nombre=row.nombre,
            correo=row.correo,
            telefono=row.telefono,
            fecha_registro=row.fecha_registro,
            asistio=row.asistio,
            asistencia_marcada_en=row.asistencia_marcada_en,
            datos_extra=row.datos_extra or {},
        )
        for row in inscritos
    ]


@router.get("/{evento_id}/inscritos-export/")
def exportar_inscritos_excel(request, evento_id: int):
    agrupacion = Agrupacion.objects.get(user=request.user)
    evento = get_object_or_404(Evento, pk=evento_id, agrupacion=agrupacion)
    inscritos = (
        Inscripcion.objects.filter(formulario__evento=evento)
        .order_by("-fecha_registro")
    )

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in evento.titulo)[:60] or "evento"
    response["Content-Disposition"] = f'attachment; filename="inscritos_{safe_name}.csv"'
    response.write("\ufeff")  # BOM para que Excel abra UTF-8 correctamente.

    # Usamos ';' para que Excel en configuracion regional ES separe columnas correctamente.
    writer = csv.writer(response, delimiter=";")
    # Respeta exactamente el orden de la tabla visible en dashboard.
    writer.writerow(["Asiste", "Nombre", "Correo"])
    for row in inscritos:
        writer.writerow(
            [
                "Si" if row.asistio else "No",
                row.nombre,
                row.correo,
            ]
        )
    return response


@router.post("/{evento_id}/inscritos/{inscripcion_id}/asistencia/")
def actualizar_asistencia(request, evento_id: int, inscripcion_id: int, payload: AsistenciaIn):
    agrupacion = Agrupacion.objects.get(user=request.user)
    evento = get_object_or_404(Evento, pk=evento_id, agrupacion=agrupacion)
    ins = get_object_or_404(Inscripcion, pk=inscripcion_id, formulario__evento=evento)
    ins.asistio = bool(payload.asistio)
    ins.asistencia_marcada_en = timezone.now() if ins.asistio else None
    ins.save(update_fields=["asistio", "asistencia_marcada_en"])
    certificado_ok = False
    if ins.asistio:
        certificado_ok = enviar_certificado_si_asistio(ins)
    return {"status": "success", "asistio": ins.asistio, "certificado_enviado": certificado_ok}


@router.post("/{evento_id}/sync-inscritos/")
def sync_inscritos(request, evento_id: int):
    agrupacion = Agrupacion.objects.get(user=request.user)
    evento = get_object_or_404(Evento, pk=evento_id, agrupacion=agrupacion)

    has_form = evento.tipo_inscripcion == "google_form" and (evento.form_externo_url or "").strip()
    has_sheet = bool((evento.sheet_respuestas_url or "").strip())

    if not has_form and not has_sheet:
        return {"status": "error", "message": "Este evento no tiene un Google Form ni un Google Sheet configurado."}

    if has_form:
        config = ConfiguracionBot.objects.filter(agrupacion=agrupacion).first()
        if not config or not config.google_refresh_token:
            return {"status": "error", "message": "Conecta Google para sincronizar inscritos del formulario."}
        imported, message = _sync_evento_desde_google_forms(evento, config)
    else:
        imported, message = _sync_evento_desde_sheet(evento)

    if imported == 0 and "completada" not in message.lower():
        return {"status": "error", "message": message}
    return {"status": "success", "importados": imported, "message": message}


@router.post("/{evento_id}/cerrar/")
def cerrar_evento(request, evento_id: int, payload: CerrarEventoIn):
    agrupacion = Agrupacion.objects.get(user=request.user)
    evento = get_object_or_404(Evento, pk=evento_id, agrupacion=agrupacion)
    data = cerrar_evento_y_generar_acta(evento, comentarios=(payload.comentarios or "").strip())
    return {"status": "success", **data}


@router.delete("/{evento_id}/")
def eliminar_evento(request, evento_id: int):
    agrupacion = Agrupacion.objects.get(user=request.user)
    evento = get_object_or_404(Evento, pk=evento_id, agrupacion=agrupacion)
    evento.delete()
    return {"status": "success"}


@router.post("/run-reminders/")
def run_reminders(request):
    agrupacion = Agrupacion.objects.get(user=request.user)
    result = ejecutar_recordatorios_eventos(agrupacion_id=agrupacion.id)
    return {"status": "success", **result}