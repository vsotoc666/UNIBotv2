from ninja import Router, Form, File
from ninja.files import UploadedFile
from .models import ConfiguracionBot, Agrupacion
from pypdf import PdfReader
import io
import traceback

router = Router()

@router.post("/bot-config/")
def configurar_bot(request, nombre_bot: str = Form(...), tono: str = Form(...), documento: UploadedFile = File(None)):
    try:
        agrupacion = Agrupacion.objects.get(user=request.user)
        config, _ = ConfiguracionBot.objects.get_or_create(agrupacion=agrupacion)
        
        config.nombre_bot = nombre_bot
        config.tono = tono

        if documento:
            texto = ""
            file_bytes = documento.read()
            pdf_file = io.BytesIO(file_bytes)
            
            reader = PdfReader(pdf_file)
            for page in reader.pages:
                extraido = page.extract_text()
                if extraido:
                    texto += extraido + "\n"
            
            config.texto_extraido = texto
            
            documento.seek(0)
            config.documento_conocimiento.save(documento.name, documento)
        else:
            config.save()
            
        return {"status": "success", "message": "Bot actualizado en Supabase"}
        
    except Exception as e:
        print("\n=== ERROR AL GUARDAR LA CONFIGURACIÓN DEL BOT ===")
        traceback.print_exc()
        print("=================================================\n")
        
        # LÍNEA CORREGIDA PARA DJANGO NINJA: Devolvemos una tupla (status_code, dict)
        return 400, {"status": "error", "message": str(e)}