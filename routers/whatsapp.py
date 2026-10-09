import os
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import Cita, Paciente, get_db
from security import verificar_autenticacion

router = APIRouter(tags=["WhatsApp & Pasarela"])

@router.post("/api/enviar-mensaje")
async def api_enviar_mensaje(req: Request):
    """Permite enviar mensajes personalizados de WhatsApp."""
    data = await req.json()
    num = data.get("number") or data.get("phone") or "+59178472875"
    texto = data.get("text") or data.get("message") or ""
    if not texto:
        raise HTTPException(status_code=400, detail="El campo 'text' es requerido")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post("http://127.0.0.1:8080/send-message", json={"number": num, "text": texto, "message": texto})
            return resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/api/whatsapp/estado")
async def api_whatsapp_estado():
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get("http://127.0.0.1:8080/status")
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "ok": True,
                    "conectado": data.get("connected", False),
                    "usuario": data.get("user"),
                    "tiene_qr": data.get("hasQR", False)
                }
    except Exception as e:
        return {"ok": False, "conectado": False, "error": str(e)}
    return {"ok": True, "conectado": False}

@router.get("/api/debug-bot")
async def api_debug_bot():
    status_diag = {"gemini_key_present": bool(os.getenv("GEMINI_API_KEY"))}
    async with httpx.AsyncClient(timeout=4.0) as client:
        try:
            r8080 = await client.get("http://127.0.0.1:8080/qr")
            status_diag["gateway_8080"] = {"status": r8080.status_code, "ok": True}
        except Exception as e:
            status_diag["gateway_8080"] = {"ok": False, "error": str(e)}

        try:
            r5005 = await client.get("http://127.0.0.1:5005/docs")
            status_diag["bot_5005"] = {"status": r5005.status_code, "ok": True}
        except Exception as e:
            status_diag["bot_5005"] = {"ok": False, "error": str(e)}

        try:
            r_wh = await client.post("http://127.0.0.1:5005/webhook", json={
                "from": "59170277520@s.whatsapp.net",
                "phone": "59170277520",
                "name": "Nicolas Debug",
                "text": "hola"
            }, timeout=10.0)
            status_diag["webhook_test"] = {"status": r_wh.status_code, "data": r_wh.json()}
        except Exception as e:
            status_diag["webhook_test"] = {"ok": False, "error": str(e)}

    return status_diag

@router.post("/api/citas/{cita_id}/pedir-resena")
async def pedir_resena_cita(
    cita_id: uuid.UUID,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verificar_autenticacion)
):
    cita = db.get(Cita, cita_id)
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    pac = db.get(Paciente, cita.paciente_id)
    if not pac or not pac.telefono:
        raise HTTPException(status_code=400, detail="El paciente no tiene un número de teléfono registrado")
    
    maps_url = getattr(settings, "CLINICA_MAPS_URL", "https://maps.app.goo.gl/qzzFhyyhs9HXLBi77")

    msg = (
        f"¡Hola, {pac.nombre}! ✨🦷\n\n"
        f"De parte de la *Dra. Pamela Pinto Suárez* y todo el equipo de *SOLDENT*, queremos agradecerte por haber asistido a tu consulta odontológica hoy.\n\n"
        f"Esperamos que tu atención haya sido muy grata. ¿Nos apoyarías compartiendo tu opinión y experiencia en nuestro perfil de Google Maps? ✨\n\n"
        f"👉 Puedes dejar tu reseña aquí:\n"
        f"{maps_url}\n\n"
        f"¡Tu opinión nos ayuda muchísimo a seguir cuidando sonrisas en Santa Cruz! Que tengas un excelente día. 💙"
    )

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post("http://127.0.0.1:8080/send-message", json={"number": pac.telefono, "text": msg, "message": msg})
            return {"ok": True, "enviado": True, "mensaje": msg}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _generar_form_pin_html(mensaje_error: str = "", accion: str = "/qr") -> str:
    err_div = f"<div class='error'>{mensaje_error}</div>" if mensaje_error else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Soldent - Acceso Seguro</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; color: #f8fafc; }}
        .card {{ position: relative; background: #1e293b; padding: 32px 28px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.4); text-align: center; max-width: 360px; width: 90%; border: 1px solid #334155; }}
        .btn-close {{ position: absolute; top: 14px; right: 14px; width: 34px; height: 34px; border-radius: 50%; background: #334155; color: #94a3b8; display: flex; align-items: center; justify-content: center; text-decoration: none; font-size: 16px; font-weight: 700; border: 1px solid #475569; }}
        .btn-close:hover {{ background: #475569; color: #f8fafc; }}
        h2 {{ color: #38bdf8; margin: 0 0 8px 0; font-size: 22px; }}
        p {{ color: #94a3b8; font-size: 14px; margin: 0 0 20px 0; line-height: 1.4; }}
        input {{ width: 100%; box-sizing: border-box; padding: 14px; font-size: 20px; text-align: center; letter-spacing: 6px; border: 2px solid #334155; border-radius: 12px; margin-bottom: 16px; background: #0f172a; color: #f8fafc; outline: none; }}
        input:focus {{ border-color: #38bdf8; }}
        button {{ width: 100%; background: #0284c7; color: white; padding: 14px; font-size: 16px; font-weight: 600; border: none; border-radius: 12px; cursor: pointer; transition: background 0.2s; }}
        button:hover {{ background: #0369a1; }}
        .btn-back {{ display: inline-block; margin-top: 16px; color: #38bdf8; text-decoration: none; font-size: 13px; font-weight: 600; }}
        .error {{ color: #f87171; font-size: 13px; margin-top: 12px; font-weight: 500; }}
    </style>
</head>
<body>
    <div class="card">
        <a href="/" class="btn-close" aria-label="Cerrar y volver a la agenda" onclick="if (window.opener) {{ window.close(); return false; }} else if (window.history.length > 1) {{ window.history.back(); return false; }}">✕</a>
        <h2>🔒 Soldent - Acceso Seguro</h2>
        <p>Ingresa el PIN de la Doctora para ver o administrar la vinculación de WhatsApp:</p>
        <form method="POST" action="{accion}">
            <input type="password" name="pin" placeholder="••••" autofocus required maxlength="10" />
            <button type="submit">Desbloquear</button>
            {err_div}
        </form>
        <div>
            <a href="/" class="btn-back" onclick="if (window.opener) {{ window.close(); return false; }} else if (window.history.length > 1) {{ window.history.back(); return false; }}">← Volver a la Agenda</a>
        </div>
    </div>
</body>
</html>"""

@router.get("/whatsapp", response_class=HTMLResponse)
@router.post("/whatsapp", response_class=HTMLResponse)
@router.get("/qr", response_class=HTMLResponse)
@router.post("/qr", response_class=HTMLResponse)
async def ver_qr_whatsapp(request: Request):
    pin = None
    if request.method == "POST":
        try:
            form = await request.form()
            pin = form.get("pin")
        except Exception:
            pass
    if not pin:
        pin = request.query_params.get("pin")

    cookie_pin = request.cookies.get("soldent_admin_pin")
    es_valido = (pin and pin.strip() == settings.DOCTORA_PIN) or (cookie_pin and cookie_pin.strip() == settings.DOCTORA_PIN)

    if not es_valido:
        err = "⚠️ PIN incorrecto. Intenta nuevamente." if pin else ""
        return HTMLResponse(content=_generar_form_pin_html(err, accion="/qr"), status_code=401 if pin else 200)

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get("http://127.0.0.1:8080/qr")
            response = HTMLResponse(content=resp.text, status_code=resp.status_code)
            response.set_cookie(key="soldent_admin_pin", value=settings.DOCTORA_PIN, max_age=86400, httponly=True)
            return response
    except Exception:
        response = HTMLResponse(
            "<!DOCTYPE html><html><head><meta http-equiv='refresh' content='3'><title>Soldent</title></head>"
            "<body style='font-family:sans-serif;text-align:center;padding-top:50px;'>"
            "<h3>Iniciando pasarela de WhatsApp... por favor espera unos segundos.</h3>"
            "</body></html>"
        )
        response.set_cookie(key="soldent_admin_pin", value=settings.DOCTORA_PIN, max_age=86400, httponly=True)
        return response

@router.get("/reset", response_class=HTMLResponse)
async def reset_whatsapp_confirm(request: Request):
    """GET /reset solo muestra una página de confirmación, NUNCA borra la sesión para evitar pre-fetching de navegadores."""
    return HTMLResponse(
        content="""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Confirmar Reinicio - Soldent</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: system-ui, sans-serif; background: #f8fafc; color: #1e293b; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }
        .card { background: white; padding: 32px 24px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.06); text-align: center; max-width: 400px; width: 100%; border: 1px solid #fee2e2; }
        h2 { color: #dc2626; margin-top: 0; }
        p { color: #64748b; font-size: 14px; line-height: 1.5; }
        .btn-danger { background: #dc2626; color: white; border: none; padding: 12px 20px; border-radius: 12px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 15px; font-size: 14px; }
        .btn-cancel { display: block; margin-top: 12px; color: #64748b; text-decoration: none; font-size: 13px; font-weight: bold; }
    </style>
</head>
<body>
    <div class="card">
        <h2>⚠️ ¿Desvincular WhatsApp?</h2>
        <p>Esta acción cerrará la sesión actual de WhatsApp y generará un nuevo código QR para escanear.</p>
        <form method="POST" action="/reset">
            <input type="hidden" name="confirmar" value="si">
            <button type="submit" class="btn-danger">Sí, cerrar sesión y generar nuevo QR</button>
        </form>
        <a href="/qr" class="btn-cancel">← Cancelar y volver al código QR</a>
    </div>
</body>
</html>"""
    )

@router.post("/reset", response_class=HTMLResponse)
async def reset_whatsapp(request: Request, pin: Optional[str] = None, confirmar: Optional[str] = None, db: Session = Depends(get_db)):
    cookie_pin = request.cookies.get("soldent_admin_pin")
    es_valido = (pin and pin.strip() == settings.DOCTORA_PIN) or (cookie_pin and cookie_pin.strip() == settings.DOCTORA_PIN)

    if not es_valido:
        err = "⚠️ PIN incorrecto. Intenta nuevamente." if pin else ""
        return HTMLResponse(content=_generar_form_pin_html(err, accion="/reset"), status_code=401 if pin else 200)

    try:
        db.execute(text("DELETE FROM agenda.whatsapp_session"))
        db.commit()
    except Exception:
        db.rollback()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post("http://127.0.0.1:8080/reset")
            response = HTMLResponse(content=resp.text, status_code=resp.status_code)
            response.set_cookie(key="soldent_admin_pin", value=settings.DOCTORA_PIN, max_age=86400, httponly=True)
            return response
    except Exception:
        response = HTMLResponse(
            "<!DOCTYPE html><html><head><meta http-equiv='refresh' content='2;url=/qr'></head>"
            "<body style='font-family:sans-serif;text-align:center;padding-top:50px;'>"
            "<h3>Sesión reiniciada. Generando nuevo código QR...</h3>"
            "</body></html>"
        )
        response.set_cookie(key="soldent_admin_pin", value=settings.DOCTORA_PIN, max_age=86400, httponly=True)
        return response
