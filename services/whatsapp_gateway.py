import asyncio
import random
import httpx
from config import settings, MENSAJE_OFICIAL_DEFAULT
from services.gemini_ai import safe_print

async def enviar_mensaje_whatsapp(numero: str, texto: str):
    """Envía un mensaje de texto a través de la pasarela Baileys/Evolution con retardo humano anti-detección."""
    # Retardo aleatorio humano (3 a 7 segundos) para simular lectura y preparación antes de responder
    delay_humano = random.uniform(3.0, 7.0)
    safe_print(f"⏳ [Antidetección] Pausa humana de lectura de {delay_humano:.1f}s antes de enviar...")
    await asyncio.sleep(delay_humano)

    url = f"{settings.EVOLUTION_API_URL}/send-message"
    texto_seguro = str(texto or MENSAJE_OFICIAL_DEFAULT).strip()
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
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

async def enviar_ubicacion_whatsapp(
    numero: str,
    latitude: float = None,
    longitude: float = None,
    name: str = None,
    address: str = None,
    url: str = None
):
    """Envía la ubicación GPS oficial de Soldent en WhatsApp como tarjeta interactiva de mapa."""
    # Breve pausa natural de 1.5s para que entre de forma secuencial tras el mensaje de texto
    await asyncio.sleep(1.5)

    lat = latitude if latitude is not None else getattr(settings, "CLINICA_LATITUD", -17.79082)
    lng = longitude if longitude is not None else getattr(settings, "CLINICA_LONGITUD", -63.18514)
    nombre_lugar = name or getattr(settings, "CLINICA_NOMBRE", "SOLDENT (Dra. Pamela Pinto)")
    dir_lugar = address or getattr(settings, "CLINICA_DIRECCION", "Calle Parapetí (o Lemoine) 407, casi esquina Vallegrande, Santa Cruz de la Sierra")
    maps_url = url or getattr(settings, "CLINICA_MAPS_URL", "https://maps.app.goo.gl/WtxX2ApFSZTdxNK67")

    gw_url = f"{settings.EVOLUTION_API_URL}/send-location"
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(gw_url, json={
                "number": numero,
                "latitude": lat,
                "longitude": lng,
                "name": nombre_lugar,
                "address": dir_lugar,
                "url": maps_url
            })
            if resp.status_code == 200:
                safe_print(f"📍 [Bot OUT Ubicación GPS] Tarjeta interactiva enviada con éxito a {numero}")
                return True
            else:
                safe_print(f"⚠️ [Bot OUT Ubicación Error] {resp.status_code}: {resp.text}")
                return False
    except Exception as e:
        safe_print(f"⚠️ [Bot OUT Ubicación Error] No se pudo enviar ubicación ({url}): {e}")
        return False
