import json
import urllib.error
import urllib.request
from typing import Optional

from apps.agrupaciones.models import ConfiguracionBot


NOTION_VERSION = "2022-06-28"


def _notion_post(token: str, payload: dict) -> dict:
    req = urllib.request.Request(
        "https://api.notion.com/v1/pages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_paragraph(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text[:1900]}}]},
    }


def crear_pagina_notion(
    *,
    config: ConfiguracionBot,
    titulo: str,
    lineas: list[str],
) -> str:
    token = (getattr(config, "notion_access_token", "") or "").strip()
    if not token:
        return ""

    children = [_build_paragraph(linea) for linea in lineas if (linea or "").strip()]
    payload = {
        "parent": {"type": "workspace", "workspace": True},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": titulo[:180]}}]}
        },
        "children": children or [_build_paragraph("Sin contenido")],
    }
    try:
        data = _notion_post(token, payload)
    except urllib.error.HTTPError:
        return ""
    except Exception:
        return ""
    return (data.get("url") or "").strip()


def crear_item_inscripcion_notion(
    *,
    config: ConfiguracionBot,
    evento_titulo: str,
    nombre: str,
    correo: str,
    telefono: str,
    prioridad: str,
) -> str:
    return crear_pagina_notion(
        config=config,
        titulo=f"Inscripción - {nombre} ({evento_titulo})",
        lineas=[
            f"Evento: {evento_titulo}",
            f"Nombre: {nombre}",
            f"Correo: {correo}",
            f"Teléfono: {telefono or '-'}",
            f"Prioridad: {prioridad}",
        ],
    )


def crear_acta_evento_notion(
    *,
    config: ConfiguracionBot,
    evento_titulo: str,
    inscritos: int,
    presentes: int,
    porcentaje_asistencia: float,
    comentarios: Optional[str],
    tareas_pendientes: list[str],
) -> str:
    lineas = [
        f"Evento: {evento_titulo}",
        f"Inscritos: {inscritos}",
        f"Presentes: {presentes}",
        f"% asistencia: {porcentaje_asistencia:.2f}%",
        "",
        "Comentarios:",
        comentarios or "Sin comentarios",
        "",
        "Tareas pendientes:",
    ]
    if tareas_pendientes:
        lineas.extend([f"- {row}" for row in tareas_pendientes])
    else:
        lineas.append("- Sin tareas pendientes")
    return crear_pagina_notion(
        config=config,
        titulo=f"Acta automática - {evento_titulo}",
        lineas=lineas,
    )
