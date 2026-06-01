import os
import jwt
from django.contrib.auth.models import User
from django.contrib.auth.backends import BaseBackend

class SupabaseAuthBackend(BaseBackend):
    def authenticate(self, request, token=None):
        if not token:
            return None
        try:
            # Decodificar el JWT de Supabase sin hacer llamadas de red
            secret = os.getenv('SUPABASE_JWT_SECRET')
            payload = jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
            
            supabase_uid = payload.get('sub')
            email = payload.get('email')

            # Sincronizar o crear el usuario en Django (usamos username = supabase_uid)
            user, created = User.objects.get_or_create(username=supabase_uid, defaults={'email': email})
            return user
        except Exception as e:
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None