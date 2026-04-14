from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from apps.eventos.models import FormularioRegistro, Inscripcion
from apps.agrupaciones.models import Agrupacion, SolicitudBot, ConfiguracionBot
import os



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
    
    context = {
        'agrupacion': agrupacion, 
        'solicitud_bot': solicitud,
        'config_bot': config_bot,
        'bot_username': os.getenv('BOT_USERNAME', 'UNIBotsito')
    }
    return render(request, 'dashboard.html', context)

def registro_evento(request, slug):
    formulario = get_object_or_404(FormularioRegistro, slug=slug)
    if request.method == 'POST':
        Inscripcion.objects.create(
            formulario=formulario, nombre=request.POST.get('nombre'),
            correo=request.POST.get('correo'), telefono=request.POST.get('telefono')
        )
        return render(request, 'registro_evento.html', {'success': True, 'evento': formulario.evento})
    return render(request, 'registro_evento.html', {'evento': formulario.evento})

def terminos_view(request):
    return render(request, 'terminos.html')

def privacidad_view(request):
    return render(request, 'privacidad.html')