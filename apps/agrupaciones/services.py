import os
from google import genai
from pypdf import PdfReader
from .models import FragmentoConocimiento


def process_pdf_rag(config_bot):
    """
    Extrae texto de un PDF, lo divide en fragmentos con overlap y genera embeddings
    con Google text-embedding-004. Almacena los vectores en Supabase via pgvector.
    """
    if not config_bot.documento_conocimiento:
        return

    # 1. Leer PDF página por página para conservar metadatos de página real
    reader = PdfReader(config_bot.documento_conocimiento)
    pages_text = []
    full_text = ""

    for page_num, page in enumerate(reader.pages):
        extracted = page.extract_text() or ""
        pages_text.append((page_num + 1, extracted))
        full_text += extracted + "\n"

    if not full_text.strip():
        print(f"[RAG] El PDF de {config_bot.agrupacion.nombre} no tiene texto extraíble (probablemente es una imagen escaneada).")
        return

    # Actualizar texto plano completo para compatibilidad / fallback
    config_bot.texto_extraido = full_text
    config_bot.save(update_fields=['texto_extraido'])

    # 2. Chunking con overlap: ~800 caracteres por chunk, 10% de solapamiento
    chunk_size = 800
    overlap = int(chunk_size * 0.10)  # 80 caracteres de solapamiento
    chunks = []  # lista de (contenido, num_pagina)

    for page_num, page_text in pages_text:
        if not page_text.strip():
            continue
        start = 0
        while start < len(page_text):
            end = start + chunk_size
            chunk = page_text[start:end]
            if len(chunk.strip()) >= 20:
                chunks.append((chunk, page_num))
            start += chunk_size - overlap

    if not chunks:
        print(f"[RAG] No se generaron fragmentos para {config_bot.agrupacion.nombre}.")
        return

    # 3. Generar embeddings y guardar en Supabase (pgvector)
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    # Limpiar fragmentos anteriores de esta agrupación
    FragmentoConocimiento.objects.filter(agrupacion=config_bot.agrupacion).delete()

    doc_name = getattr(config_bot.documento_conocimiento, 'name', 'documento.pdf').split('/')[-1]

    for i, (chunk, page_num) in enumerate(chunks):
        try:
            response = client.models.embed_content(
                model='text-embedding-004',
                contents=chunk
            )
            embedding_vector = response.embeddings[0].values

            FragmentoConocimiento.objects.create(
                agrupacion=config_bot.agrupacion,
                contenido=chunk,
                metadata={
                    'chunk_index': i,
                    'page_number': page_num,
                    'source_file': doc_name,
                    'total_chunks': len(chunks),
                },
                embedding=embedding_vector
            )
        except Exception as e:
            print(f"[RAG] Error generando embedding para fragmento {i} (pág {page_num}): {e}")

    print(f"[RAG] ✅ Procesados {len(chunks)} fragmentos para {config_bot.agrupacion.nombre}.")


def get_relevant_context(agrupacion, query, top_k=3):
    """
    Vectoriza la consulta del usuario y busca los fragmentos más similares
    en Supabase usando distancia coseno (pgvector). Retorna texto concatenado.
    """
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    try:
        response = client.models.embed_content(
            model='text-embedding-004',
            contents=query
        )
        query_vector = response.embeddings[0].values

        from pgvector.django import CosineDistance

        relevant_chunks = (
            FragmentoConocimiento.objects
            .filter(agrupacion=agrupacion)
            .annotate(distance=CosineDistance('embedding', query_vector))
            .order_by('distance')[:top_k]
        )

        results = list(relevant_chunks)
        if not results:
            return ""

        return "\n---\n".join([c.contenido for c in results])

    except Exception as e:
        print(f"[RAG] Error en búsqueda semántica: {e}")
        return ""
