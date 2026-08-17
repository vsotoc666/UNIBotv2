# UNIBot v2

Plataforma web + bot de Telegram para que agrupaciones/organizaciones universitarias gestionen
eventos de principio a fin: creación y publicación en Google Calendar, inscripciones (propias o
vía Google Forms), control de asistencia, certificados automáticos, recordatorios, y
automatizaciones hacia Notion y ClipUp (ClickUp). Incluye un bot de Telegram con RAG
(Retrieval-Augmented Generation) que responde preguntas públicas sobre los eventos usando Gemini,
con filtros de seguridad para no exponer datos internos ni información de asistentes.

## Tabla de contenidos

- [Características](#características)
- [Arquitectura y stack](#arquitectura-y-stack)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Requisitos previos](#requisitos-previos)
- [Instalación y configuración local](#instalación-y-configuración-local)
- [Variables de entorno](#variables-de-entorno)
- [Google Cloud OAuth (flujo local)](#google-cloud-oauth-flujo-local)
- [Bot de Telegram](#bot-de-telegram)
- [Tareas en background (Django Q)](#tareas-en-background-django-q)
- [Seguridad](#seguridad)
- [Roadmap / limitaciones conocidas](#roadmap--limitaciones-conocidas)

## Características

### Integraciones OAuth
- Conexión/desconexión con **Google** (correo + Calendar), **Notion** y **ClipUp**.
- Estado visual de cada integración en el dashboard (conectado / no conectado).
- Configuración de Google Calendar desde el dashboard (activar/desactivar y `calendar_id`).

### Gestión de eventos
- Creación de eventos con validación de fechas (`fecha_fin > fecha_inicio`).
- Publicación automática en Google Calendar al crear el evento.
- Link público de inscripción por evento.

### Inscripciones y asistencia
- Tipo de inscripción configurable por evento: formulario interno o **Google Form** externo.
- Sincronización de inscritos desde la Google Forms API.
- Tabla de inscritos por evento y marcado de asistencia.
- Exportación a CSV (`Asiste / Nombre / Correo`) lista para Excel.

### Correos automáticos
- Correo de confirmación al inscribirse.
- Envío vía **Gmail API** (OAuth) con fallback a **SMTP** personal.
- Estado de confirmación guardado por inscripción.

### Automatizaciones
- **Post-inscripción**: correo de confirmación + tarea en ClipUp + ítem en Notion + prioridad automática.
- **Cierre de evento**: resumen de inscritos/presentes/porcentaje de asistencia, comentarios, tareas
  pendientes del equipo y acta generada en Notion.
- **Certificados**: al marcar `asistio = true` se genera un PDF, se envía por correo y se registra la referencia.
- **Recordatorios inteligentes**: envío a 24h y 2h antes del evento, sin reenvíos duplicados y con
  mensaje distinto para primera convocatoria vs. recordatorio recurrente.

### Bot de Telegram con RAG
- Responde preguntas usando contexto de los eventos/agrupación (Gemini + `pgvector` en Supabase).
- Bloqueo explícito de respuestas sobre datos de inscritos, arquitectura interna, integraciones
  (Notion/ClipUp) o credenciales/tokens.
- Solo responde información pública del evento (hora, tema, link de inscripción, etc.).

## Arquitectura y stack

| Capa | Tecnología |
|---|---|
| Backend web | [Django](https://www.djangoproject.com/) 5.x |
| API | [django-ninja](https://django-ninja.dev/) |
| Tareas en background | [django-q2](https://django-q2.readthedocs.io/) (usa la BD como broker, sin Redis) |
| Bot de Telegram | [python-telegram-bot](https://python-telegram-bot.org/) |
| RAG / IA | [google-genai](https://pypi.org/project/google-genai/) (Gemini) + `pgvector` |
| Base de datos | PostgreSQL (Supabase), vía `dj-database-url` |
| Auth | Supabase Auth (backend de autenticación propio) + OAuth 2.0 de Google |
| Storage de archivos | Supabase Storage (API S3) vía `django-storages` + `boto3` |
| Integraciones externas | Google Calendar, Gmail, Google Forms, Notion API, ClipUp (ClickUp) API |

## Estructura del proyecto

```
UNIBotv2/
├── backend/                # Configuración del proyecto Django (settings, urls, wsgi/asgi)
├── apps/
│   ├── core/                # Vistas generales: landing, dashboard, OAuth (Google/Notion/ClipUp)
│   ├── users/                # Autenticación (Supabase), middleware multi-tenant, modelos de usuario
│   ├── agrupaciones/         # Agrupaciones/organizaciones, configuración del bot, contexto RAG
│   ├── eventos/              # Eventos, inscripciones, asistencia, certificados, correos, Notion/ClipUp
│   └── bot/                  # Bot de Telegram y lógica de RAG + filtros de seguridad
├── manage.py
├── requirements.txt
└── .env                      # Variables de entorno (no se sube al repo)
```

## Requisitos previos

- Python 3.11+ (recomendado)
- Una base de datos PostgreSQL con la extensión `pgvector` habilitada (se usa [Supabase](https://supabase.com/))
- Un bot de Telegram (token vía [@BotFather](https://t.me/BotFather)) si vas a probar el bot
- Credenciales OAuth 2.0 de Google Cloud (tipo Web) para login y Calendar
- (Opcional) Credenciales de integración con Notion y ClipUp

## Instalación y configuración local

1. Clona el repositorio y crea/actualiza tu archivo `.env` en la raíz con tus credenciales
   (ver [Variables de entorno](#variables-de-entorno)).
2. Abre una terminal en la raíz del proyecto.
3. Crea el entorno virtual e instala las dependencias:
   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
4. Ejecuta las migraciones:
   ```powershell
   python manage.py migrate
   ```
5. Levanta el servidor de desarrollo:
   ```powershell
   python manage.py runserver
   ```
6. (Opcional) Levanta el worker de tareas en background en otra terminal:
   ```powershell
   python manage.py qcluster
   ```
7. (Opcional) Levanta el bot de Telegram (ver comando específico en
   `apps/bot/management/commands/`).

## Variables de entorno

Crea un archivo `.env` en la raíz del proyecto con las siguientes claves:

```dotenv
# Django
DJANGO_SECRET_KEY=
DEBUG=True
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000

# Base de datos (Supabase Postgres)
DATABASE_URL=

# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=
SUPABASE_STORAGE_BUCKET=

# Storage (S3 compatible, Supabase)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_S3_ENDPOINT_URL=

# Google (login, Calendar, Gmail, Forms)
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback/

# Notion
NOTION_CLIENT_ID=
NOTION_CLIENT_SECRET=
NOTION_REDIRECT_URI=

# Telegram
TELEGRAM_BOT_TOKEN=
BOT_USERNAME=

# Gemini / RAG
GEMINI_API_KEY=
```

> ⚠️ **Nunca subas tu `.env` al repositorio.** Ya está excluido en `.gitignore`.

## Google Cloud OAuth (flujo local)

Para poder iniciar sesión con Google en local, configura tu cliente OAuth 2.0 (tipo Web):

1. Google Cloud → **APIs y servicios** → **Credenciales**.
2. Abre tu cliente OAuth.
3. En **"Authorized redirect URIs"** agrega:
   ```
   http://127.0.0.1:8000/auth/google/callback/
   ```
4. En tu `.env`, configura:
   ```dotenv
   GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback/
   ```

### Limitación temporal (sin dominio público verificado)

Mientras el proyecto no tenga un dominio público, la pantalla de consentimiento de Google OAuth
puede quedar en modo de prueba. En ese escenario, para autenticarte con Google debes permitir
manualmente las cuentas que iniciarán sesión:

1. Google Cloud → **APIs y servicios** → **Pantalla de consentimiento OAuth**.
2. En **"Usuarios de prueba"** agrega el correo que quieres autorizar.
3. Guarda los cambios y vuelve a intentar el login OAuth.

Esto es temporal para desarrollo/equipo interno. Cuando exista un dominio público y la app se
publique correctamente, este paso manual deja de ser necesario.

## Bot de Telegram

El bot vive en `apps/bot/telegram_bot.py` y usa el contexto de la agrupación/eventos
(`apps.agrupaciones.services.get_relevant_context`) junto con Gemini para responder preguntas.
Antes de responder, filtra preguntas sensibles y, además, revisa que la respuesta generada no
filtre información interna (ver [Seguridad](#seguridad)). Configura `TELEGRAM_BOT_TOKEN` y
`BOT_USERNAME` en tu `.env` para activarlo.

## Tareas en background (Django Q)

Los recordatorios, certificados y automatizaciones de correo/Notion/ClipUp se procesan de forma
asíncrona con `django-q2`, usando la propia base de datos como broker (sin dependencia de Redis).
Corre el cluster de workers con:

```powershell
python manage.py qcluster
```

## Seguridad

- El bot de Telegram bloquea explícitamente respuestas sobre datos de inscritos, arquitectura
  interna, integraciones (Notion/ClipUp) o tokens/credenciales/configuración sensible, y solo
  permite información pública del evento (hora, tema, link, etc.).
- Un middleware multi-tenant (`apps.users.middleware.SupabaseTenantMiddleware`) aísla los datos por
  agrupación a nivel de base de datos.
- Los secretos viven exclusivamente en variables de entorno (`.env`, nunca versionado).

## Roadmap / limitaciones conocidas

- El login con Google requiere agregar manualmente "usuarios de prueba" hasta contar con un
  dominio público verificado (ver sección de OAuth arriba).
- Pendiente: publicación de la app de Google Cloud fuera de modo de prueba una vez exista dominio
  público.
