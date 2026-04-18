import os
from google import genai
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from asgiref.sync import sync_to_async
from django.utils import timezone
from apps.bot.models import TelegramChat
from apps.agrupaciones.models import Agrupacion, ConfiguracionBot
from apps.agrupaciones.services import get_relevant_context
from apps.eventos.models import Evento


@sync_to_async
def asociar_chat_a_agrupacion(chat_id: str, uuid_str: str):
    try:
        agrupacion = Agrupacion.objects.get(uuid=uuid_str)
        TelegramChat.objects.update_or_create(
            chat_id=chat_id,
            defaults={'agrupacion': agrupacion}
        )
        return agrupacion.nombre
    except Agrupacion.DoesNotExist:
        return None


@sync_to_async
def obtener_contexto_tenant(chat_id: str):
    try:
        asociacion = TelegramChat.objects.get(chat_id=chat_id)
        agrupacion = asociacion.agrupacion
        config = ConfiguracionBot.objects.get(agrupacion=agrupacion)

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

    # 1. Recuperar el Tenant (Agrupación) desde el Chat ID de Telegram
    config, eventos = await obtener_contexto_tenant(chat_id)

    if not config:
        await update.message.reply_text(
            "⚠️ Aún no estás asociado a ninguna agrupación o el administrador no "
            "ha configurado la IA. Usa el enlace del Dashboard web para conectarte."
        )
        return

    # 2. RAG: obtener fragmentos de conocimiento semánticamente relevantes
    contexto_rag = await sync_to_async(get_relevant_context)(
        config.agrupacion, update.message.text
    )

    # 3. Construir lista de eventos próximos del Tenant
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

    # 4. Construir prompt inyectado con contexto RAG + eventos
    contexto_conocimiento = contexto_rag if contexto_rag else config.texto_extraido
    prompt = f"""Eres '{config.nombre_bot}', un asistente virtual exclusivo de la agrupación '{config.agrupacion.nombre}'.
Tu tono de respuesta DEBE SER estrictamente: {config.tono}.

CONOCIMIENTO OFICIAL DE LA AGRUPACIÓN (Contexto RAG):
---
{contexto_conocimiento}
---

EVENTOS ACTIVOS (proporciona el link si preguntan por inscripciones):
---
{eventos_str}
---

REGLA ESTRICTA: Responde solo con información de la agrupación y sus eventos provista arriba. Si te preguntan algo fuera de contexto, indícalo amablemente y redirígelos a los temas de la agrupación.

Consulta del usuario: {update.message.text}"""

    # 5. Generar respuesta con Gemini 2.5 Flash
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    try:
        response = await sync_to_async(client.models.generate_content)(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        await update.message.reply_text(response.text)
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

    print("🤖 UNIBot (Multi-Tenant RAG) iniciado. Presiona Ctrl+C para detener.")
    app.run_polling()
