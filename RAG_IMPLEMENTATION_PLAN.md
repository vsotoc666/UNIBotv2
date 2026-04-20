# Plan de Implementación RAG v2 - UNIBot (Multi-Documento)

Este documento detalla la arquitectura y el estado de la implementación del sistema de Generación Aumentada por Recuperación (RAG) con soporte para múltiples archivos PDF.

## 🚀 Estado Actual: **COMPLETADO** ✅

### 1. Arquitectura de Datos (Supabase + pgvector)
- [x] **Modelo Multi-Documento:** Se implementó `DocumentoConocimiento` para permitir N archivos por agrupación.
- [x] **Vectores Vinculados:** Los fragmentos (`FragmentoConocimiento`) ahora tienen una relación `ForeignKey` con su documento de origen.
- [x] **Limpieza Granular:** Al eliminar un documento, se eliminan automáticamente solo sus vectores asociados (vía CASCADE).
- [x] **Dimensiones:** Configurado a 768 dimensiones para compatibilidad total con Gemini.

### 2. Procesamiento de IA (Google Gemini)
- [x] **Modelo Confirmado:** Uso de `models/gemini-embedding-001` (Estable y compatible).
- [x] **Manejo de Cuota (429):** Implementado `time.sleep(0.8)` para respetar el límite de 100 peticiones/minuto del Plan Gratuito.
- [x] **Chunking:** División de texto en bloques de 800 caracteres con 10% de solapamiento para mantener el contexto entre fragmentos.

### 3. Backend e Infraestructura (Django + Django-Q)
- [x] **Tareas Asíncronas:** Uso de `django-q2` con el ORM como broker (eliminando dependencia de Redis).
- [x] **Signals:** Disparo automático del entrenamiento al subir cualquier archivo a la biblioteca.

### 4. Interfaz de Usuario (Dashboard)
- [x] **Biblioteca de Conocimiento:** Interfaz Vue.js que permite gestionar múltiples archivos.
- [x] **Feedback en Tiempo Real:** Labels dinámicos que muestran "Entrenando..." y "Listo" mediante polling automático cada 5 segundos.

---

## 🔮 Próximos Pasos y Recomendaciones

### A Corto Plazo (Optimización)
1. **Soporte de Formatos:** Expandir el procesador para aceptar archivos `.docx` y `.txt` además de PDFs.
2. **Historial de Chat:** Implementar una memoria de corto plazo (últimos 5 mensajes) en Telegram para que el bot pueda seguir el hilo de la conversación.
3. **Feedback de Usuario:** Añadir botones de "👍/👎" en Telegram para guardar las respuestas que fueron útiles y mejorar el conocimiento.

### A Mediano Plazo (Escalabilidad)
1. **Caché de Embeddings:** Implementar un sistema de caché (Redis) para consultas frecuentes del bot, ahorrando llamadas a la API de Gemini.
2. **Reranking:** Implementar un modelo de "Rerank" después de la búsqueda semántica para asegurar que los fragmentos pasados a la IA sean los más precisos posibles.
3. **Optimización de Chunks:** Ajustar el tamaño del bloque (800 chars) según el tipo de documento (ej. los reglamentos legales funcionan mejor con bloques más pequeños y específicos).

### Recomendaciones de Seguridad y Costos
1. **Protección de Datos (PII):** Implementar un filtro que detecte y oculte DNI o correos electrónicos sensibles dentro de los documentos antes de enviarlos a la IA.
2. **Límites de Uso:** Configurar una cuota máxima de archivos por agrupación (ej. máximo 10 PDFs de 5MB) para evitar costos excesivos de almacenamiento en Supabase.
3. **Monitoreo:** Usar herramientas como LangSmith o similares para monitorear qué tan bien está funcionando el RAG y detectar "alucinaciones" de la IA.

---
*Última actualización: 20 de Abril, 2026*
