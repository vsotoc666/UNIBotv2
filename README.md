# UNIBot v2

## Instalacion y configuracion local

### 5 pasos (equipo)

1. Clona el repo y crea/actualiza `.env` con tus credenciales.
2. Abre PowerShell en la raiz del proyecto.
3. Crea entorno virtual e instala dependencias:
   - `py -3 -m venv .venv`
   - `.\.venv\Scripts\Activate.ps1`
   - `pip install -r requirements.txt`
4. Ejecuta migraciones:
   - `python manage.py migrate`
5. Levanta la app:
   - `python manage.py runserver`

### Google Cloud OAuth (flujo local)

Para login con Google en local, revisa tu cliente OAuth 2.0 (tipo web):

1. Google Cloud -> APIs y servicios -> Credenciales.
2. Abre tu cliente OAuth.
3. En "Authorized redirect URIs" agrega:
   - `http://127.0.0.1:8000/auth/google/callback/`
4. En `.env`, configura:
   - `GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback/`

### Limitacion temporal (sin dominio publico verificado)

Mientras el proyecto no tenga dominio publico, Google OAuth puede quedar en modo prueba.
En ese escenario, para autenticarte con Google debes permitir manualmente las cuentas que van a iniciar sesion:

1. Google Cloud -> APIs y servicios -> Pantalla de consentimiento OAuth.
2. En "Usuarios de prueba" agrega el correo que quieres autorizar.
3. Guarda cambios y vuelve a intentar login OAuth.

Esto es temporal para desarrollo/equipo interno.
Cuando ya exista dominio publico y la app se publique correctamente, este paso manual se elimina y la autenticacion sera normal para usuarios finales.


## Avances implementados (semana)

### 1) Integraciones OAuth y panel de integraciones
- Conexion/desconexion con:
  - Google (correo + Calendar)
  - Notion
  - ClipUp
- Estado visual en dashboard: conectado/no conectado.
- Configuracion de Google Calendar desde dashboard (activar/desactivar y `calendar_id`).

### 2) Gestion de eventos mejorada
- Creacion de eventos con validacion de fechas (`fecha_fin > fecha_inicio`).
- Publicacion en Google Calendar al crear evento.
- Prevencion del error `timeRangeEmpty` (ajuste defensivo en backend).
- Links publicos de inscripcion por evento.

### 3) Inscripciones y asistencia
- Configuracion de tipo de inscripcion por evento:
  - formulario interno
  - Google Form externo
- Sincronizacion de inscritos desde Google Forms API.
- Tabla de inscritos por evento.
- Marcado de asistencia por inscrito.
- Exportacion CSV para Excel (`Asiste / Nombre / Correo`).

### 4) Correos automaticos
- Confirmacion de inscripcion por correo.
- Envio por:
  - Gmail API (OAuth)
  - fallback a SMTP personal
- Estado de confirmacion guardado por inscripcion.

### 5) ClipUp funcional
- Carga real de listas/workspaces desde API.
- Seleccion y guardado de lista destino en dashboard.
- Creacion de tarea en ClipUp por inscripcion (flujo automatico).

### 6) Notion funcional
- Creacion de paginas en Notion para registro automatico.
- Generacion de acta de cierre de evento en Notion.

### 7) Automatizaciones nuevas (producto real)
- Flujo post-inscripcion:
  - correo de confirmacion
  - tarea ClipUp
  - item en Notion
  - prioridad automatica
- Cierre de evento:
  - inscritos, presentes, porcentaje de asistencia
  - comentarios
  - tareas pendientes del equipo
  - acta en Notion
- Certificados:
  - al marcar `asistio = true`
  - genera PDF
  - envia por correo
  - registra referencias
- Recordatorios inteligentes:
  - envio a 24h y 2h antes del evento
  - evita reenvios duplicados
  - diferencia mensaje para primera vez vs recurrente

### 8) Seguridad de respuestas del bot (Telegram + RAG)
- Bloqueo de respuestas sobre:
  - datos de inscritos
  - arquitectura interna
  - Notion/ClipUp internos
  - tokens/credenciales/configuracion sensible
- Permitido solo: informacion publica de eventos (hora, tema, link, etc.).



