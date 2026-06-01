import os
import unicodedata
from google import genai
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from asgiref.sync import sync_to_async
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.bot.models import TelegramChat
from apps.agrupaciones.models import Agrupacion, ConfiguracionBot
from apps.agrupaciones.services import get_relevant_context
from apps.eventos.models import Evento

SAFE_FALLBACK_REPLY = (
    "Por seguridad y privacidad, no puedo compartir datos personales ni información interna "
    "de arquitectura, integraciones o configuración. "
    "Sí puedo ayudarte con información pública del evento: fecha, hora, descripción y link de inscripción."
)

def _normalize_text(value: str) -> str:
    raw = (value or "").strip().lower()
    no_accents = "".join(
        ch for ch in unicodedata.normalize("NFKD", raw) if not unicodedata.combining(ch)
    )
    return no_accents

def _is_sensitive_question(user_text: str) -> bool:
    text = _normalize_text(user_text)
    sensitive_hits = [
        # Enumeración de datos personales de otros (no términos generales como "correo").
        "lista de inscritos", "lista de asistentes", "lista de participantes",
        "dame los datos", "datos de los inscritos", "datos de los asistentes",
        "correo de los inscritos", "correo de los asistentes",
        "telefono de los inscritos", "telefono de los asistentes",
        "datos personales", "dni", "celular de",
        # Integraciones internas.
        "notion", "clipup", "clickup", "webhook",
        # Secretos/credenciales.
        "token", "access token", "clave secreta", "password", "contrasena",
        "credencial", "api key", "oauth", "refresh token", "client secret", "client id",
        # Arquitectura e infraestructura interna.
        "supabase", "postgres", "postgresql", "base de datos",
        "backend", "servidor interno", "hosting", "aws", "s3", "redis", "django",
        "endpoint interno", "arquitectura", "infraestructura",
        "como funciona internamente", "stack tecnico", "codigo fuente", "logs",
    ]
    return any(hit in text for hit in sensitive_hits)

def _response_leaks_sensitive_data(answer: str) -> bool:
    text = _normalize_text(answer)
    suspicious = [
        # Integraciones y arquitectura.
        "supabase", "postgres", "postgresql", "django", "backend",
        "notion", "clipup", "clickup", "oauth", "webhook",
        # Secretos/credenciales (no "@" porque es legítimo en links/handles públicos).
        "token", "refresh_token", "api_key", "client_secret", "client_id",
        "contrasena", "password",
    ]
    return any(hit in text for hit in suspicious)

@sync_to_async
def asociar_chat_a_agrupacion(chat_id: str, uuid_str: str):
    try:
        agrupacion = Agrupacion.objects.get(uuid=uuid_str)
        # Deep Linking: Crea o actualiza la asociación
        TelegramChat.objects.update_or_create(
            chat_id=chat_id,
            defaults={'agrupacion': agrupacion}
        )
        return agrupacion.nombre
    except (Agrupacion.DoesNotExist, ValidationError, ValueError):
        return None

@sync_to_async
def obtener_contexto_tenant(chat_id: str):
    try:
        asociacion = TelegramChat.objects.get(chat_id=chat_id)
        agrupacion = asociacion.agrupacion
        # Cargamos agrupación en la misma query para evitar lecturas lazy en contexto async.
        config = ConfiguracionBot.objects.select_related("agrupacion").get(agrupacion=agrupacion)
        
        # Obtenemos eventos SOLO de este Tenant
        eventos = list(Evento.objects.filter(
            agrupacion=agrupacion, 
            fecha_inicio__gte=timezone.now()
        ).select_related('formularioregistro'))
        
        return config, eventos
    except (TelegramChat.DoesNotExist, ConfiguracionBot.DoesNotExist):
        return None, None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    args = context.args

    if not args:
        await update.message.reply_text(
            "👋 ¡Hola! Soy UNIBot.\n"
            "Para usarme, necesitas hacer clic en el enlace de Telegram "
            "que aparece en el Dashboard web de tu agrupación."
        )
        return

    uuid_str = args[0]
    nombre_agrupacion = await asociar_chat_a_agrupacion(chat_id, uuid_str)
    
    if nombre_agrupacion:
        await update.message.reply_text(
            f"✅ ¡Enlazado exitosamente a la agrupación: *{nombre_agrupacion}*!\n\n"
            "Puedes hacerme preguntas sobre eventos o reglamentos y te responderé.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Enlace inválido o la agrupación no existe.")

async def responder_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    
    # 1. Recuperamos el Tenant (Agrupación) desde el Chat ID
    config, eventos = await obtener_contexto_tenant(chat_id)
    
    if not config:
        await update.message.reply_text(
            "⚠️ Aún no estás asociado a ninguna agrupación o el administrador no "
            "ha configurado la IA. Usa el enlace del Dashboard web para conectarte."
        )
        return
        
    user_question = update.message.text or ""
    
    # 2. Control de seguridad pre-prompt
    if _is_sensitive_question(user_question):
        await update.message.reply_text(SAFE_FALLBACK_REPLY)
        return

    # 3. RAG: obtener fragmentos de conocimiento semánticamente relevantes
    contexto_rag = await sync_to_async(get_relevant_context)(
        config.agrupacion, user_question
    )

    # 4. Construimos la lista de eventos dinámica del Tenant
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:8000")
    lista_eventos = []
    for e in eventos:
        try:
            slug = await sync_to_async(lambda ev: ev.formularioregistro.slug)(e)
            lista_eventos.append(
                f"- {e.titulo} (Inicia: {e.fecha_inicio.strftime('%Y-%m-%d %H:%M')}). "
                f"Registro: {base_url}/evento/registro/{slug}/"
            )
        except Exception:
            lista_eventos.append(
                f"- {e.titulo} (Inicia: {e.fecha_inicio.strftime('%Y-%m-%d %H:%M')}). "
                "(Formulario de registro no disponible)"
            )
    
    eventos_str = "\n".join(lista_eventos) if lista_eventos else "No hay eventos próximos programados."

    # 5. Construir prompt inyectado con RAG + Reglas de Seguridad
    contexto_conocimiento = contexto_rag if contexto_rag else config.texto_extraido
    
    prompt = f"""
    Eres '{config.nombre_bot}', un asistente virtual exclusivo de la agrupación '{config.agrupacion.nombre}'.
    Tu tono de respuesta DEBE SER estrictamente: {config.tono}.
    
    CONOCIMIENTO OFICIAL DE LA AGRUPACIÓN (Contexto RAG):
    ---
    {contexto_conocimiento}
    ---
    
    EVENTOS ACTIVOS (Dales el link si preguntan por inscripciones):
    ---
    {eventos_str}
    ---

    REGLA ESTRICTA:
    - Responde solo con información pública de la agrupación y eventos provista arriba.
    - NUNCA reveles datos de inscritos/asistentes (nombres, correos, teléfonos, DNI u otros datos personales).
    - NUNCA reveles información de integraciones internas (Notion, ClipUp/ClickUp, tokens, claves, OAuth, credenciales).
    - Si preguntan por datos sensibles, rechaza amablemente y ofrece solo datos públicos del evento (hora, fecha, descripción, link de inscripción).
    
    Consulta del usuario: {user_question}
    """

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    
    try:
        response = await sync_to_async(client.models.generate_content)(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        answer = (response.text or "").strip()
        
        # 6. Control de seguridad post-prompt
        if not answer or _response_leaks_sensitive_data(answer):
            await update.message.reply_text(SAFE_FALLBACK_REPLY)
            return
            
        await update.message.reply_text(answer)
    except Exception as e:
        print(f"[Bot] Error de IA: {e}")
        await update.message.reply_text(
            "Lo siento, tuve un problema procesando tu respuesta con IA. "
            "Por favor intenta de nuevo en un momento."
        )

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN no está configurado en las variables de entorno.")

    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_mensaje))
    
    print("🤖 UNIBot (Multi-Tenant RAG + Seguridad) iniciado. Presiona Ctrl+C para detener.")
    app.run_polling()