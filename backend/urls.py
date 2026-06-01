from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from ninja import NinjaAPI

# Vistas Generales y de Eventos
from apps.core.views import (
    landing, dashboard_view, registro_evento, 
    terminos_view, privacidad_view, google_oauth_start, google_oauth_callback,
    notion_oauth_start, notion_oauth_callback, clipup_oauth_start, clipup_oauth_callback
)

# ¡NUEVO! Importamos las vistas de Supabase en lugar de las antiguas
from apps.users.views import (
    supabase_login_view, 
    supabase_register_view, 
    supabase_logout_view
)

from apps.agrupaciones.api import router as agrupaciones_router
from apps.eventos.api import router as eventos_router

api = NinjaAPI(csrf=True)
api.add_router("/agrupaciones/", agrupaciones_router)
api.add_router("/eventos/", eventos_router)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', landing, name='landing'),
    
    # --- RUTAS DE AUTENTICACIÓN (Conectadas a Supabase) ---
    # Mantenemos los name='login' y name='register' para no romper el HTML
    path('login/', supabase_login_view, name='login'),
    path('registro/', supabase_register_view, name='register'),
    path('logout/', supabase_logout_view, name='logout'),
    
    # Rutas Legales
    path('terminos/', terminos_view, name='terminos'),
    path('privacidad/', privacidad_view, name='privacidad'),
    
    # Rutas de la App
    path('dashboard/', dashboard_view, name='dashboard'),
    path('auth/google/start/', google_oauth_start, name='google_oauth_start'),
    path('auth/google/callback/', google_oauth_callback, name='google_oauth_callback'),
    path('auth/notion/start/', notion_oauth_start, name='notion_oauth_start'),
    path('auth/notion/callback/', notion_oauth_callback, name='notion_oauth_callback'),
    path('auth/clipup/start/', clipup_oauth_start, name='clipup_oauth_start'),
    path('auth/clipup/callback/', clipup_oauth_callback, name='clipup_oauth_callback'),
    path('evento/registro/<uuid:slug>/', registro_evento, name='registro_evento'),
    
    path('api/', api.urls),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)