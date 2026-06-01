from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils import timezone
from apps.eventos.models import FormularioRegistro, Inscripcion
from apps.eventos.automation import ejecutar_flujo_post_inscripcion
from apps.agrupaciones.models import Agrupacion, SolicitudBot, ConfiguracionBot
import os
import json
import secrets
import base64
from urllib.parse import urlencode
from urllib.request import Request, urlopen



def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'landing.html')

def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            Agrupacion.objects.create(user=user, nombre=f"Agrupación de {user.username}")
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('landing')

@login_required
def dashboard_view(request):
    agrupacion = Agrupacion.objects.get(user=request.user)
    
    # --- LA MAGIA NUEVA: Escuchar al botón "Activar UNIBot" ---
    if request.method == 'POST' and 'solicitar_bot' in request.POST:
        # 1. Creamos la solicitud (la marcamos aprobada por defecto para el MVP)
        SolicitudBot.objects.get_or_create(agrupacion=agrupacion, defaults={'aprobado': True})
        
        # 2. Creamos su perfil de configuración básico para que no de error
        ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)
        
        # 3. Recargamos la página limpiamente
        return redirect('dashboard')
    # -----------------------------------------------------------

    solicitud = SolicitudBot.objects.filter(agrupacion=agrupacion).first()
    config_bot = ConfiguracionBot.objects.filter(agrupacion=agrupacion).first()
    
    bot_username = os.getenv('BOT_USERNAME', 'UNIBotsito')
    telegram_link = f"https://t.me/{bot_username}?start={agrupacion.uuid}" if solicitud else ""
    context = {
        'agrupacion': agrupacion,
        'solicitud_bot': solicitud,
        'config_bot': config_bot,
        'bot_username': bot_username,
        'telegram_link': telegram_link,
        'google_oauth_status': request.GET.get('google_oauth', ''),
        'notion_oauth_status': request.GET.get('notion_oauth', ''),
        'clipup_oauth_status': request.GET.get('clipup_oauth', ''),
    }
    return render(request, 'dashboard.html', context)


@login_required
def google_oauth_start(request):
    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    redirect_uri = (os.getenv("GOOGLE_REDIRECT_URI") or "").strip()
    if not client_id or not redirect_uri:
        return redirect(f"{reverse('dashboard')}?google_oauth=missing_config")

    state = secrets.token_urlsafe(24)
    request.session["google_oauth_state"] = state
    request.session["google_oauth_state_ts"] = timezone.now().isoformat()

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/forms.responses.readonly https://www.googleapis.com/auth/forms.body.readonly",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return redirect(auth_url)


@login_required
def google_oauth_callback(request):
    state = request.GET.get("state", "")
    expected_state = request.session.get("google_oauth_state", "")
    if not state or state != expected_state:
        return redirect(f"{reverse('dashboard')}?google_oauth=state_error")

    code = request.GET.get("code", "")
    if not code:
        return redirect(f"{reverse('dashboard')}?google_oauth=cancelled")

    client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.getenv("GOOGLE_REDIRECT_URI") or "").strip()
    if not client_id or not client_secret or not redirect_uri:
        return redirect(f"{reverse('dashboard')}?google_oauth=missing_config")

    token_payload = urlencode(
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")

    try:
        token_req = Request(
            "https://oauth2.googleapis.com/token",
            data=token_payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(token_req, timeout=15) as response:
            token_data = json.loads(response.read().decode("utf-8"))

        access_token = (token_data.get("access_token") or "").strip()
        refresh_token = (token_data.get("refresh_token") or "").strip()
        if not access_token:
            return redirect(f"{reverse('dashboard')}?google_oauth=token_error")

        userinfo_req = Request(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        with urlopen(userinfo_req, timeout=15) as response:
            userinfo = json.loads(response.read().decode("utf-8"))
        google_email = (userinfo.get("email") or "").strip()

        agrupacion = Agrupacion.objects.get(user=request.user)
        config, _ = ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)
        config.google_email = google_email
        if refresh_token:
            config.google_refresh_token = refresh_token
        config.google_connected_at = timezone.now()
        if google_email:
            config.correo_remitente = google_email
        config.clave_app_remitente = ""
        config.save(
            update_fields=[
                "google_email",
                "google_refresh_token",
                "google_connected_at",
                "correo_remitente",
                "clave_app_remitente",
            ]
        )
    except Exception:
        return redirect(f"{reverse('dashboard')}?google_oauth=token_error")
    finally:
        request.session.pop("google_oauth_state", None)
        request.session.pop("google_oauth_state_ts", None)

    return redirect(f"{reverse('dashboard')}?google_oauth=connected")


@login_required
def notion_oauth_start(request):
    client_id = (os.getenv("NOTION_CLIENT_ID") or "").strip()
    redirect_uri = (os.getenv("NOTION_REDIRECT_URI") or "").strip()
    if not client_id or not redirect_uri:
        return redirect(f"{reverse('dashboard')}?notion_oauth=missing_config")

    state = secrets.token_urlsafe(24)
    request.session["notion_oauth_state"] = state

    params = {
        "owner": "user",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    auth_url = f"https://api.notion.com/v1/oauth/authorize?{urlencode(params)}"
    return redirect(auth_url)


@login_required
def notion_oauth_callback(request):
    state = request.GET.get("state", "")
    expected_state = request.session.get("notion_oauth_state", "")
    if not state or state != expected_state:
        return redirect(f"{reverse('dashboard')}?notion_oauth=state_error")

    code = request.GET.get("code", "")
    if not code:
        return redirect(f"{reverse('dashboard')}?notion_oauth=cancelled")

    client_id = (os.getenv("NOTION_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("NOTION_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.getenv("NOTION_REDIRECT_URI") or "").strip()
    if not client_id or not client_secret or not redirect_uri:
        return redirect(f"{reverse('dashboard')}?notion_oauth=missing_config")

    basic_token = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    payload = json.dumps(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")

    try:
        token_req = Request(
            "https://api.notion.com/v1/oauth/token",
            data=payload,
            headers={
                "Authorization": f"Basic {basic_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urlopen(token_req, timeout=20) as response:
            token_data = json.loads(response.read().decode("utf-8"))

        access_token = (token_data.get("access_token") or "").strip()
        if not access_token:
            return redirect(f"{reverse('dashboard')}?notion_oauth=token_error")

        workspace_id = (token_data.get("workspace_id") or "").strip()
        workspace_name = (token_data.get("workspace_name") or "").strip()

        agrupacion = Agrupacion.objects.get(user=request.user)
        config, _ = ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)
        config.notion_access_token = access_token
        config.notion_workspace_id = workspace_id
        config.notion_workspace_name = workspace_name
        config.notion_connected_at = timezone.now()
        config.save(
            update_fields=[
                "notion_access_token",
                "notion_workspace_id",
                "notion_workspace_name",
                "notion_connected_at",
            ]
        )
    except Exception:
        return redirect(f"{reverse('dashboard')}?notion_oauth=token_error")
    finally:
        request.session.pop("notion_oauth_state", None)

    return redirect(f"{reverse('dashboard')}?notion_oauth=connected")


@login_required
def clipup_oauth_start(request):
    client_id = (os.getenv("CLIPUP_CLIENT_ID") or "").strip()
    redirect_uri = (os.getenv("CLIPUP_REDIRECT_URI") or "").strip()
    if not client_id or not redirect_uri:
        return redirect(f"{reverse('dashboard')}?clipup_oauth=missing_config")

    state = secrets.token_urlsafe(24)
    request.session["clipup_oauth_state"] = state

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    auth_url = f"https://app.clickup.com/api?{urlencode(params)}"
    return redirect(auth_url)


@login_required
def clipup_oauth_callback(request):
    state = request.GET.get("state", "")
    expected_state = request.session.get("clipup_oauth_state", "")
    if not state or state != expected_state:
        return redirect(f"{reverse('dashboard')}?clipup_oauth=state_error")

    code = request.GET.get("code", "")
    if not code:
        return redirect(f"{reverse('dashboard')}?clipup_oauth=cancelled")

    client_id = (os.getenv("CLIPUP_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("CLIPUP_CLIENT_SECRET") or "").strip()
    redirect_uri = (os.getenv("CLIPUP_REDIRECT_URI") or "").strip()
    if not client_id or not client_secret or not redirect_uri:
        return redirect(f"{reverse('dashboard')}?clipup_oauth=missing_config")

    payload = json.dumps(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
        }
    ).encode("utf-8")

    try:
        token_req = Request(
            "https://api.clickup.com/api/v2/oauth/token",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(token_req, timeout=20) as response:
            token_data = json.loads(response.read().decode("utf-8"))

        access_token = (token_data.get("access_token") or "").strip()
        if not access_token:
            return redirect(f"{reverse('dashboard')}?clipup_oauth=token_error")

        # Validamos que el token realmente funciona antes de guardarlo.
        user_req = Request(
            "https://api.clickup.com/api/v2/user",
            headers={"Authorization": access_token},
            method="GET",
        )
        with urlopen(user_req, timeout=20):
            pass

        agrupacion = Agrupacion.objects.get(user=request.user)
        config, _ = ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)
        config.clipup_api_token = access_token
        config.clipup_connected_at = timezone.now()
        config.clipup_enabled = False
        config.save(update_fields=["clipup_api_token", "clipup_connected_at", "clipup_enabled"])
    except Exception:
        return redirect(f"{reverse('dashboard')}?clipup_oauth=token_error")
    finally:
        request.session.pop("clipup_oauth_state", None)

    return redirect(f"{reverse('dashboard')}?clipup_oauth=connected")

def registro_evento(request, slug):
    formulario = get_object_or_404(FormularioRegistro, slug=slug)
    evento = formulario.evento
    if evento.tipo_inscripcion == "google_form" and evento.form_externo_url:
        return redirect(evento.form_externo_url)
    if request.method == 'POST':
        inscripcion = Inscripcion.objects.create(
            formulario=formulario, nombre=request.POST.get('nombre'),
            correo=request.POST.get('correo'), telefono=request.POST.get('telefono')
        )
        ejecutar_flujo_post_inscripcion(inscripcion)
        return render(request, 'registro_evento.html', {'success': True, 'evento': evento})
    return render(request, 'registro_evento.html', {'evento': evento})

def terminos_view(request):
    return render(request, 'terminos.html')

def privacidad_view(request):
    return render(request, 'privacidad.html')