import os
import jwt
from django.db import connection
from django.contrib.auth.models import User
from django.contrib.auth import login

class SupabaseTenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Extraer JWT de la cookie HttpOnly
        token = request.COOKIES.get('sb-access-token')
        
        if token and not request.user.is_authenticated:
            try:
                secret = os.getenv('SUPABASE_JWT_SECRET')
                payload = jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
                user = User.objects.filter(username=payload.get('sub')).first()
                if user:
                    login(request, user, backend='apps.users.auth_backend.SupabaseAuthBackend')
            except jwt.ExpiredSignatureError:
                pass # Token expirado
            except Exception:
                pass # Token inválido

        # 2. Configurar el Tenant ID para RLS en PostgreSQL
        # Si es el bot (telegram_bot.py no pasa por vistas web), esto se ignora.
        with connection.cursor() as cursor:
            if request.user.is_authenticated:
                tenant_id = str(request.user.id)
                # SET LOCAL aplica solo a esta transacción (protegido por ATOMIC_REQUESTS)
                cursor.execute("SET LOCAL app.tenant_id = %s;", [tenant_id])
            else:
                cursor.execute("SET LOCAL app.tenant_id = '';")

        response = self.get_response(request)
        return response