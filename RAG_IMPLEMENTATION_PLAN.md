# UNIBot — Guía Técnica Completa: RAG Multi-Tenant con Supabase + Gemini

**Proyecto:** Proyecto4_CISUNI  
**Stack:** Django 5 · Supabase (PostgreSQL + pgvector + S3) · Google Gemini · Telegram  
**Estado actual:** ✅ RAG completamente funcional

---

## ¿Qué es RAG y por qué lo usamos?

**RAG (Retrieval-Augmented Generation)** es una técnica que combina búsqueda semántica con generación de texto. En lugar de pedirle al LLM que "recuerde" información, primero buscamos los fragmentos más relevantes de nuestros documentos y los inyectamos en el prompt. Esto elimina las "alucinaciones" y permite que el bot responda con información propia de cada agrupación.

```
Pregunta del usuario
        │
        ▼
Vectorizar pregunta (Gemini text-embedding-004)
        │
        ▼
Buscar top-3 fragmentos similares en Supabase (pgvector)
        │
        ▼
Construir prompt: [Sistema] + [Fragmentos RAG] + [Eventos] + [Pregunta]
        │
        ▼
Generar respuesta (Gemini 2.5 Flash)
        │
        ▼
Respuesta en Telegram
```

---

## Arquitectura Multi-Tenant

Cada **Agrupación** (club/organización universitaria) tiene su propio espacio aislado:

```
Agrupacion (tenant)
│
├── ConfiguracionBot       ← nombre del bot, tono, PDF subido
│   └── documento_conocimiento  → guardado en Supabase Storage (S3)
│
├── FragmentoConocimiento  ← chunks del PDF con sus embeddings (768-dim)
│   metadata: {page_number, chunk_index, source_file, total_chunks}
│
├── TelegramChat           ← asocia un chat_id de Telegram a esta agrupación
│
└── Evento                 ← eventos próximos con formulario de inscripción
```

El aislamiento se garantiza a dos niveles:
1. **Django ORM**: todos los queries filtran por `agrupacion=agrupacion`
2. **Supabase RLS**: el middleware establece `SET LOCAL app.tenant_id` por cada request HTTP

---

## Tecnologías y para qué sirve cada una

| Componente | Tecnología | Función en el proyecto |
|---|---|---|
| Framework web | Django 5 | Estructura MVC, ORM, admin, auth |
| API REST | django-ninja | Endpoints tipados con Pydantic para el dashboard |
| Base de datos | Supabase (PostgreSQL) | Almacena todos los modelos |
| Búsqueda vectorial | pgvector (extensión Postgres) | Guarda embeddings de 768 dims y busca por similitud coseno |
| Almacenamiento de PDFs | Supabase Storage (S3) | Guarda los PDFs subidos por cada agrupación |
| Embeddings | Google text-embedding-004 | Convierte texto en vectores de 768 dimensiones |
| LLM | Google Gemini 2.5 Flash | Genera respuestas en lenguaje natural |
| Bot de mensajería | python-telegram-bot 21 | Interface de usuario para miembros de la agrupación |
| Tareas async | django-q2 | Procesa PDFs en background sin bloquear al usuario |
| Autenticación | Supabase Auth + JWT | Login/registro de administradores de agrupaciones |
| ORM + S3 | django-storages + boto3 | Sube archivos a Supabase Storage transparentemente |

---

## Flujo completo: de PDF a respuesta en Telegram

### Fase 1 — Indexación (cuando el admin sube un PDF)

```
Admin sube PDF desde el Dashboard web
        │
        ▼
api.py::configurar_bot()
  ├── Extrae texto con pypdf (sync, para texto_extraido inmediato)
  └── Guarda en ConfiguracionBot.documento_conocimiento
             → django-storages sube el archivo a Supabase Storage (S3)
             → post_save signal se dispara
                      │
                      ▼
             signals.py::trigger_rag_processing()
               └── django-q2: async_task('process_pdf_rag', instance)
                          │ (el admin ya recibió la respuesta HTTP)
                          ▼
             services.py::process_pdf_rag()
               ├── Abre PDF desde S3 con PdfReader
               ├── Extrae texto por página
               ├── Chunking con overlap 10%
               │     chunk_size = 800 chars
               │     overlap    =  80 chars
               ├── Por cada chunk:
               │     Gemini text-embedding-004 → vector [768 floats]
               └── FragmentoConocimiento.objects.create(
                     agrupacion, contenido, metadata, embedding)
```

### Fase 2 — Consulta (cuando un miembro escribe en Telegram)

```
Miembro escribe en Telegram: "¿Cuándo es el próximo taller?"
        │
        ▼
telegram_bot.py::responder_mensaje()
  │
  ├── obtener_contexto_tenant(chat_id)
  │     → TelegramChat → Agrupacion → ConfiguracionBot + Eventos
  │
  ├── get_relevant_context(agrupacion, query)
  │     ├── Gemini text-embedding-004 vectoriza la query
  │     └── pgvector CosineDistance → top-3 fragmentos más cercanos
  │
  ├── Construir lista de eventos próximos con links de registro
  │
  ├── Prompt final:
  │     Eres '{nombre_bot}', asistente de '{agrupacion}'...
  │     Tono: {tono}
  │     [FRAGMENTOS RAG]
  │     [EVENTOS]
  │     Pregunta: {query}
  │
  └── Gemini 2.5 Flash → respuesta → Telegram
```

---

## Deep Linking: cómo un miembro se conecta a su agrupación

Cada agrupación tiene un UUID único. El Dashboard web muestra un enlace:

```
https://t.me/NombreDelBot?start=<UUID-de-la-agrupación>
```

Cuando el miembro hace clic y abre Telegram:
1. Telegram envía `/start <UUID>` al bot
2. `start_command()` llama a `asociar_chat_a_agrupacion(chat_id, uuid)`
3. Se crea o actualiza `TelegramChat(chat_id=..., agrupacion=...)`
4. Desde ese momento, todos los mensajes de ese `chat_id` van al contexto de esa agrupación

---

## Archivos clave del RAG

| Archivo | Responsabilidad |
|---|---|
| [apps/agrupaciones/models.py](apps/agrupaciones/models.py) | `FragmentoConocimiento` con `VectorField(dimensions=768)` |
| [apps/agrupaciones/services.py](apps/agrupaciones/services.py) | `process_pdf_rag()` y `get_relevant_context()` |
| [apps/agrupaciones/signals.py](apps/agrupaciones/signals.py) | Dispara el procesamiento async cuando se guarda un PDF |
| [apps/agrupaciones/api.py](apps/agrupaciones/api.py) | Endpoint POST que recibe el PDF del dashboard |
| [apps/bot/telegram_bot.py](apps/bot/telegram_bot.py) | Lógica del bot: deep linking, RAG, generación con Gemini |

---

## Setup inicial — Pasos en orden

### 1. Supabase: habilitar pgvector

En el **SQL Editor** de tu proyecto Supabase:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Sin esto, las migraciones fallarán al crear `VectorField`.

### 2. Variables de entorno

Copia `.env.example` a `.env` y completa todos los campos:

```bash
cp .env.example .env
```

| Variable | Dónde obtenerla |
|---|---|
| `DJANGO_SECRET_KEY` | Genera con `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DATABASE_URL` | Supabase → Project Settings → Database → Connection string (Transaction pooler) |
| `SUPABASE_JWT_SECRET` | Supabase → Project Settings → API → JWT Secret |
| `AWS_ACCESS_KEY_ID` | Supabase → Project Settings → Storage → S3 Access |
| `AWS_SECRET_ACCESS_KEY` | Igual que arriba |
| `AWS_S3_ENDPOINT_URL` | `https://<project-ref>.supabase.co/storage/v1/s3` |
| `SUPABASE_STORAGE_BUCKET` | Nombre del bucket creado en Supabase Storage (ej: `pdfs`) |
| `TELEGRAM_BOT_TOKEN` | BotFather en Telegram → `/newbot` |
| `GEMINI_API_KEY` | Google AI Studio → API Keys |
| `BASE_URL` | `http://127.0.0.1:8000` en dev, tu dominio en producción |

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Migraciones

```bash
python manage.py makemigrations
python manage.py migrate
```

### 5. Crear superusuario (admin Django)

```bash
python manage.py createsuperuser
```

### 6. Levantar los 3 procesos necesarios

En terminales separadas:

```bash
# Terminal 1: Servidor web Django
python manage.py runserver

# Terminal 2: Worker de tareas (procesa PDFs en background)
python manage.py qcluster

# Terminal 3: Bot de Telegram
python manage.py runbot
```

---

## Funcionalidades actualmente operativas

### ✅ Autenticación de Administradores
- Registro e inicio de sesión via Supabase Auth
- JWT en cookies HttpOnly, decodificado localmente (sin red)
- RLS por tenant en cada request

### ✅ Dashboard de Agrupación
- Configurar nombre del bot y tono (amigable / formal / técnico)
- Subir PDF de conocimiento (máx 5MB)
- Ver enlace de deep linking para compartir con miembros

### ✅ Procesamiento RAG de PDFs
- Extracción de texto página por página con pypdf
- Chunking con overlap del 10% para evitar cortes de contexto
- Generación de embeddings con `text-embedding-004` (768 dims)
- Almacenamiento en Supabase con pgvector
- Metadata: `{page_number, chunk_index, source_file, total_chunks}`
- Procesamiento asíncrono con django-q2 (no bloquea al usuario)

### ✅ Bot de Telegram Multi-Tenant
- Deep linking por UUID: cada agrupación tiene su enlace único
- Búsqueda semántica por distancia coseno al recibir un mensaje
- Fallback a `texto_extraido` si el RAG no tiene fragmentos aún
- Inyección dinámica de eventos próximos con links de inscripción
- Tono configurable por agrupación

### ✅ Gestión de Eventos
- Crear eventos con fecha y hora
- Formulario de inscripción auto-generado con slug único
- Links de registro inyectados en las respuestas del bot

---

## Posibles mejoras futuras

### Calidad del RAG
- **Re-ranking**: usar un modelo cross-encoder para reordenar los top-K resultados antes de inyectarlos
- **Chunking semántico**: dividir por párrafos o secciones en lugar de por caracteres fijos
- **Soporte multi-formato**: agregar docx, txt, markdown con librerías como `python-docx` o `markdown`
- **PDFs escaneados**: integrar OCR con `pytesseract` o la API de Document AI de Google para PDFs de imágenes

### Escalabilidad
- **Índice HNSW en pgvector**: para búsquedas más rápidas con muchos fragmentos
  ```sql
  CREATE INDEX ON agrupaciones_fragmentoconocimiento 
  USING hnsw (embedding vector_cosine_ops);
  ```
- **Caché de embeddings de queries**: Redis para queries frecuentes
- **top_k configurable**: exponer como campo en `ConfiguracionBot`

### Observabilidad
- Loggear qué fragmentos se recuperaron por query (para auditoría y mejora)
- Endpoint GET para ver estado del índice RAG de cada agrupación
- Endpoint DELETE para limpiar y reindexar manualmente

### Producción
- Reemplazar `python manage.py runbot` por un servicio systemd o contenedor Docker
- Usar `gunicorn` + `nginx` para el servidor web
- Configurar webhooks de Telegram (en lugar de polling) para menor latencia
- Agregar `ALLOWED_HOSTS` con el dominio real en `settings.py`

---

## Troubleshooting frecuente

**El bot no responde / dice "no estás asociado"**
→ Verificar que el miembro usó el enlace de deep linking del Dashboard.
→ Verificar `TelegramChat.objects.filter(chat_id=<id>)` en el admin Django.

**El RAG no encuentra contexto relevante**
→ Verificar que el worker `qcluster` está corriendo cuando se sube el PDF.
→ Verificar `FragmentoConocimiento.objects.filter(agrupacion=...)` en el admin.
→ El PDF puede ser una imagen escaneada; en ese caso `pypdf` extrae texto vacío.

**Error al subir PDF (S3)**
→ Verificar `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` y `AWS_S3_ENDPOINT_URL` en `.env`.
→ Verificar que el bucket `pdfs` existe y tiene política pública de lectura en Supabase.

**Error `operator does not exist: vector <=> double precision[]`**
→ La extensión `vector` no está habilitada en Supabase. Ejecutar `CREATE EXTENSION IF NOT EXISTS vector;`.

**Error `No module named 'pgvector'`**
→ Ejecutar `pip install pgvector>=0.3.0` o `pip install -r requirements.txt`.

---

*Actualizado: 2026-04-18*
