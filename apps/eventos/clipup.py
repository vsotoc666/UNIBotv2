import json
import urllib.request

from apps.agrupaciones.models import ConfiguracionBot


def crear_tarea_clipup_desde_inscripcion(inscripcion) -> bool:
    if not inscripcion:
        return False
    evento = inscripcion.formulario.evento
    config = ConfiguracionBot.objects.filter(agrupacion=evento.agrupacion).first()
    if not config or not config.clipup_enabled:
        return False

    token = (config.clipup_api_token or "").strip()
    list_id = (config.clipup_list_id or "").strip()
    if not token or not list_id:
        return False

    payload = {
        "name": f"Inscrito: {inscripcion.nombre} - {evento.titulo}",
        "description": (
            f"Evento: {evento.titulo}\n"
            f"Correo: {inscripcion.correo}\n"
            f"Telefono: {inscripcion.telefono}\n"
            f"Asistio: {'Si' if inscripcion.asistio else 'No'}\n"
            f"Registro: {inscripcion.fecha_registro}"
        ),
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.clickup.com/api/v2/list/{list_id}/task",
        data=body,
        headers={
            "Authorization": (token or "").replace("Bearer ", "").strip(),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            status_code = getattr(response, "status", None) or response.getcode()
        return int(status_code) in (200, 201)
    except Exception:
        return False
