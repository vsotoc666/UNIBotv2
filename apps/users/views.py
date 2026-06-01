import os
from supabase import create_client, Client
from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from apps.agrupaciones.models import Agrupacion

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_ANON_KEY")
supabase: Client = create_client(url, key)

def supabase_login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            
            # --- EL BLINDAJE CRÍTICO ---
            # 1. Aseguramos que el usuario exista en la base de datos local de Django
            user, _ = User.objects.get_or_create(username=response.user.id, defaults={'email': email})
            
            # 2. Inyectamos la sesión nativa de Django (Esto evita que el middleware te rebote)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            # ---------------------------

            res = redirect('dashboard')
            res.set_cookie(
                'sb-access-token',
                response.session.access_token,
                httponly=True,
                secure=False, # False para Localhost
                samesite='Lax',
                max_age=response.session.expires_in
            )
            return res
        except Exception as e:
            print(f"Error de Login Supabase: {e}") # Para ver el error real en la consola
            return render(request, 'login.html', {'error': 'Credenciales inválidas'})
    return render(request, 'login.html')

def supabase_register_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        nombre_agrupacion = request.POST.get('nombre_agrupacion')
        try:
            response = supabase.auth.sign_up({"email": email, "password": password})
            
            if response.user and not response.user.identities:
                return render(request, 'register.html', {'error': 'Este correo ya está registrado en el sistema. Por favor, inicia sesión.'})

            user, _ = User.objects.get_or_create(username=response.user.id, defaults={'email': email})
            Agrupacion.objects.get_or_create(user=user, defaults={'nombre': nombre_agrupacion})

            session = response.session
            
            if not session:
                try:
                    login_res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    session = login_res.session
                except Exception:
                    return render(request, 'register.html', {'error': 'Cuenta creada con éxito. Revisa tu correo.'})

            # --- EL BLINDAJE CRÍTICO ---
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            # ---------------------------

            res = redirect('dashboard')
            res.set_cookie(
                'sb-access-token', session.access_token,
                httponly=True, 
                secure=False, 
                samesite='Lax',
                max_age=session.expires_in
            )
            return res
            
        except Exception as e:
            error_msg = str(e)
            if "Password should be" in error_msg:
                error_msg = "La contraseña es muy débil."
            elif "User already registered" in error_msg:
                error_msg = "Este correo ya está registrado."
            return render(request, 'register.html', {'error': error_msg})
            
    return render(request, 'register.html')

def supabase_logout_view(request):
    logout(request)
    response = redirect('landing')
    response.delete_cookie('sb-access-token')
    return response