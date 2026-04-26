from ninja import Router, Form, File, Schema
from ninja.files import UploadedFile
from .models import ConfiguracionBot, Agrupacion
from pypdf import PdfReader
import io
import traceback
import json
from urllib.request import Request, urlopen
from django.utils import timezone

router = Router()


class GoogleCalendarConfigIn(Schema):
    enabled: bool = False
    calendar_id: str = ""


class ClipUpConfigIn(Schema):
    enabled: bool = False
    list_id: str = ""

@router.post("/bot-config/")
def configurar_bot(
    request,
    nombre_bot: str = Form(...),
    tono: str = Form(...),
    correo_remitente: str = Form(""),
    documento: UploadedFile = File(None),
):
    try:
        agrupacion = Agrupacion.objects.get(user=request.user)
        config, _ = ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)
        
        config.nombre_bot = nombre_bot
        config.tono = tono
        config.correo_remitente = (correo_remitente or "").strip()
        # Si ya tiene OAuth de Google conectado, mantenemos ese remitente como fuente principal.
        if config.google_refresh_token and config.google_email:
            config.correo_remitente = config.google_email

        if documento:
            texto = ""
            file_bytes = documento.read()
            pdf_file = io.BytesIO(file_bytes)
            
            reader = PdfReader(pdf_file)
            for page in reader.pages:
                extraido = page.extract_text()
                if extraido:
                    texto += extraido + "\n"
            
            config.texto_extraido = texto
            
            documento.seek(0)
            config.documento_conocimiento.save(documento.name, documento)
        else:
            config.save()
            
        return {"status": "success", "message": "Bot actualizado en Supabase"}
        
    except Exception as e:
        print("\n=== ERROR AL GUARDAR LA CONFIGURACIÓN DEL BOT ===")
        traceback.print_exc()
        print("=================================================\n")
        
        # LÍNEA CORREGIDA PARA DJANGO NINJA: Devolvemos una tupla (status_code, dict)
        return 400, {"status": "error", "message": str(e)}


@router.get("/google-status/")
def google_status(request):
    agrupacion = Agrupacion.objects.get(user=request.user)
    config = ConfiguracionBot.objects.filter(agrupacion=agrupacion).first()
    connected = bool(config and config.google_refresh_token and config.google_email)
    return {
        "connected": connected,
        "email": (getattr(config, "google_email", "") or ""),
        "connected_at": getattr(config, "google_connected_at", None),
    }


@router.post("/google-disconnect/")
def google_disconnect(request):
    agrupacion = Agrupacion.objects.get(user=request.user)
    config, _ = ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)
    config.google_email = ""
    config.google_refresh_token = ""
    config.google_connected_at = None
    config.google_calendar_enabled = False
    config.google_calendar_id = ""
    config.correo_remitente = ""
    config.clave_app_remitente = ""
    config.save(
        update_fields=[
            "google_email",
            "google_refresh_token",
            "google_connected_at",
            "google_calendar_enabled",
            "google_calendar_id",
            "correo_remitente",
            "clave_app_remitente",
        ]
    )
    return {"status": "success", "message": "Cuenta de Google desconectada"}


@router.post("/notion-disconnect/")
def notion_disconnect(request):
    agrupacion = Agrupacion.objects.get(user=request.user)
    config, _ = ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)
    config.notion_access_token = ""
    config.notion_workspace_id = ""
    config.notion_workspace_name = ""
    config.notion_connected_at = None
    config.save(
        update_fields=[
            "notion_access_token",
            "notion_workspace_id",
            "notion_workspace_name",
            "notion_connected_at",
        ]
    )
    return {"status": "success", "message": "Cuenta de Notion desconectada"}


@router.post("/google-calendar-config/")
def google_calendar_config(request, payload: GoogleCalendarConfigIn):
    agrupacion = Agrupacion.objects.get(user=request.user)
    config, _ = ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)
    if not config.google_refresh_token or not config.google_email:
        return 400, {"status": "error", "message": "Primero conecta tu cuenta de Google."}

    enabled = bool(payload.enabled)
    calendar_id = (payload.calendar_id or "").strip() or (config.google_email or "").strip()
    if enabled and not calendar_id:
        return 400, {"status": "error", "message": "No se encontró un calendario de Google válido."}

    config.google_calendar_enabled = enabled
    config.google_calendar_id = calendar_id if enabled else ""
    config.save(update_fields=["google_calendar_enabled", "google_calendar_id"])
    return {"status": "success", "message": "Configuración de Google Calendar guardada"}


@router.post("/clipup-config/")
def clipup_config(request, payload: ClipUpConfigIn):
    agrupacion = Agrupacion.objects.get(user=request.user)
    config, _ = ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)

    enabled = bool(payload.enabled)
    list_id = (payload.list_id or "").strip()
    if not config.clipup_api_token:
        return 400, {"status": "error", "message": "Primero conecta ClipUp con OAuth."}
    if enabled and not list_id:
        return 400, {"status": "error", "message": "Selecciona una lista de ClipUp."}

    config.clipup_enabled = enabled
    config.clipup_list_id = list_id if enabled else ""
    if enabled and not config.clipup_connected_at:
        config.clipup_connected_at = timezone.now()
    config.save(
        update_fields=[
            "clipup_enabled",
            "clipup_list_id",
            "clipup_connected_at",
        ]
    )
    return {"status": "success", "message": "Integración ClipUp guardada"}


@router.post("/clipup-disconnect/")
def clipup_disconnect(request):
    agrupacion = Agrupacion.objects.get(user=request.user)
    config, _ = ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)
    config.clipup_enabled = False
    config.clipup_api_token = ""
    config.clipup_list_id = ""
    config.clipup_connected_at = None
    config.save(
        update_fields=[
            "clipup_enabled",
            "clipup_api_token",
            "clipup_list_id",
            "clipup_connected_at",
        ]
    )
    return {"status": "success", "message": "ClipUp desconectado"}


def _clipup_get_json(url: str, token: str):
    cleaned_token = (token or "").replace("Bearer ", "").strip()
    req = Request(url, headers={"Authorization": cleaned_token}, method="GET")
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


@router.get("/clipup-lists/")
def clipup_lists(request):
    agrupacion = Agrupacion.objects.get(user=request.user)
    config = ConfiguracionBot.objects.filter(agrupacion=agrupacion).first()
    token = (getattr(config, "clipup_api_token", "") or "").strip()
    if not token:
        return 400, {"status": "error", "message": "ClipUp no está conectado."}

    try:
        # En OAuth de ClickUp, los workspaces se listan en /team (no siempre vienen en /user).
        team_data = _clipup_get_json("https://api.clickup.com/api/v2/team", token)
        teams = team_data.get("teams") or []
        resultado = []

        for team in teams:
            team_id = str(team.get("id") or "").strip()
            team_name = (team.get("name") or "Workspace").strip()
            if not team_id:
                continue

            spaces_data = _clipup_get_json(f"https://api.clickup.com/api/v2/team/{team_id}/space?archived=false", token)
            for space in spaces_data.get("spaces") or []:
                space_id = str(space.get("id") or "").strip()
                space_name = (space.get("name") or "Space").strip()
                if not space_id:
                    continue

                direct_lists = _clipup_get_json(f"https://api.clickup.com/api/v2/space/{space_id}/list?archived=false", token)
                for item in direct_lists.get("lists") or []:
                    list_id = str(item.get("id") or "").strip()
                    list_name = (item.get("name") or "List").strip()
                    if not list_id:
                        continue
                    resultado.append(
                        {
                            "id": list_id,
                            "name": list_name,
                            "label": f"{team_name} / {space_name} / {list_name}",
                        }
                    )

                folders_data = _clipup_get_json(f"https://api.clickup.com/api/v2/space/{space_id}/folder?archived=false", token)
                for folder in folders_data.get("folders") or []:
                    folder_id = str(folder.get("id") or "").strip()
                    folder_name = (folder.get("name") or "Folder").strip()
                    if not folder_id:
                        continue
                    folder_lists = _clipup_get_json(f"https://api.clickup.com/api/v2/folder/{folder_id}/list?archived=false", token)
                    for item in folder_lists.get("lists") or []:
                        list_id = str(item.get("id") or "").strip()
                        list_name = (item.get("name") or "List").strip()
                        if not list_id:
                            continue
                        resultado.append(
                            {
                                "id": list_id,
                                "name": list_name,
                                "label": f"{team_name} / {space_name} / {folder_name} / {list_name}",
                            }
                        )

        return {"status": "success", "lists": resultado}
    except Exception:
        return 400, {"status": "error", "message": "No se pudieron cargar listas de ClipUp."}