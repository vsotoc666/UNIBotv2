import os
import time
from google import genai
from pypdf import PdfReader
from .models import FragmentoConocimiento, DocumentoConocimiento


def process_pdf_rag(documento):
    """
    Extrae texto de un DocumentoConocimiento, lo divide en fragmentos y genera embeddings.
    Implementa control de velocidad para no agotar la cuota de Google.
    """
    # Verificar que el documento aún exista en la DB (por si se borró rápido)
    if not DocumentoConocimiento.objects.filter(id=documento.id).exists():
        return

    if not documento.archivo:
        return

    # 1. Leer PDF
    reader = PdfReader(documento.archivo)
    pages_text = []
    full_text = ""

    for page_num, page in enumerate(reader.pages):
        extracted = page.extract_text() or ""
        pages_text.append((page_num + 1, extracted))
        full_text += extracted + "\n"

    if not full_text.strip():
        print(f"[RAG] El PDF '{documento.nombre}' no tiene texto extraíble.")
        return

    # 2. Chunking
    chunks = []
    chunk_size = 800
    overlap = 80

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

    # 3. Embeddings y Guardado
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    # Limpiar fragmentos anteriores SOLO de este documento
    FragmentoConocimiento.objects.filter(documento=documento).delete()

    for i, (chunk, page_num) in enumerate(chunks):
        try:
            # Control de velocidad: evitar el error 429 de Google
            time.sleep(0.8)

            response = client.models.embed_content(
                model='gemini-embedding-001',
                contents=chunk,
                config={'output_dimensionality': 768}
            )
            embedding_vector = response.embeddings[0].values

            # Re-verificar si el documento sigue existiendo antes de crear fragmento
            if not DocumentoConocimiento.objects.filter(id=documento.id).exists():
                print(f"[RAG] Deteniendo: el documento {documento.nombre} ya no existe.")
                return

            FragmentoConocimiento.objects.create(
                agrupacion=documento.agrupacion,
                documento=documento,
                contenido=chunk,
                metadata={
                    'chunk_index': i,
                    'page_number': page_num,
                    'source_file': documento.nombre,
                    'total_chunks': len(chunks),
                },
                embedding=embedding_vector
            )
        except Exception as e:
            print(f"[RAG] Error en fragmento {i} de {documento.nombre}: {e}")
            if "429" in str(e):
                print("[RAG] ⚠️ Límite de cuota alcanzado. Esperando 15s...")
                time.sleep(15)

    try:
        if DocumentoConocimiento.objects.filter(id=documento.id).exists():
            documento.procesado = True
            documento.save(update_fields=['procesado'])
            print(f"[RAG] ✅ '{documento.nombre}' procesado ({len(chunks)} fragmentos).")
    except Exception:
        pass


def get_relevant_context(agrupacion, query, top_k=3):
    """
    Vectoriza la consulta del usuario y busca los fragmentos más similares
    en Supabase usando distancia coseno (pgvector). Retorna texto concatenado.
    """
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    try:
        response = client.models.embed_content(
            model='gemini-embedding-001',
            contents=query,
            config={'output_dimensionality': 768}
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
