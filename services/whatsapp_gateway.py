import httpx
from config import settings, MENSAJE_OFICIAL_DEFAULT
from services.gemini_ai import safe_print

async def enviar_mensaje_whatsapp(numero: str, texto: str):
    """Envía un mensaje de texto a través de la pasarela Baileys/Evolution asegurando texto válido."""
    url = f"{settings.EVOLUTION_API_URL}/send-message"
    texto_seguro = str(texto or MENSAJE_OFICIAL_DEFAULT).strip()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json={
                "number": numero,
                "text": texto_seguro,
                "message": texto_seguro
            })
            if resp.status_code == 200:
                safe_print(f"[Bot OUT] Enviado con éxito a {numero}")
            else:
                safe_print(f"[Bot OUT Error] {resp.status_code}: {resp.text}")
    except Exception as e:
        safe_print(f"[Bot OUT Error] No se pudo conectar con la pasarela WhatsApp ({url}): {e}")
