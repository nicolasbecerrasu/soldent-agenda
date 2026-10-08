import hashlib
import hmac
import time as std_time
from typing import Optional
from fastapi import Header, HTTPException, Request, status
from config import settings

def generar_auth_token() -> str:
    timestamp = int(std_time.time())
    mensaje = f"dra_pamela:{timestamp}"
    firma = hmac.new(settings.SECRET_KEY.encode(), mensaje.encode(), hashlib.sha256).hexdigest()
    return f"{mensaje}:{firma}"

def validar_auth_token(token: str) -> bool:
    if not token:
        return False
    partes = token.split(":")
    if len(partes) != 3:
        return False
    user, ts_str, firma = partes
    if user != "dra_pamela":
        return False
    try:
        ts = int(ts_str)
        # Token válido por 90 días en el dispositivo de la doctora
        if std_time.time() - ts > (90 * 86400):
            return False
    except Exception:
        return False
    esperada = hmac.new(settings.SECRET_KEY.encode(), f"{user}:{ts_str}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(firma, esperada)

def verificar_autenticacion(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_auth_token: Optional[str] = Header(None)
):
    # Permitir peticiones internas locales (del bot de WhatsApp que corre en el mismo servidor)
    client_host = request.client.host if request.client else ""
    if client_host in ("127.0.0.1", "localhost", "::1"):
        return True

    if x_auth_token == settings.SECRET_KEY:
        return True

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif x_auth_token:
        token = x_auth_token.strip()

    if not token or not validar_auth_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acceso restringido. Por favor ingrese el PIN de la Doctora."
        )
    return True

def es_telefono_bolivia_valido(tel: Optional[str]) -> bool:
    if not tel:
        return False
    digitos = "".join(c for c in tel if c.isdigit())
    if digitos.startswith("59199"):
        return False
    if len(digitos) == 11 and digitos.startswith("591") and digitos[3] in ("6", "7"):
        return True
    if len(digitos) == 8 and digitos[0] in ("6", "7"):
        return True
    return False

def normalizar_telefono(tel: Optional[str]) -> Optional[str]:
    if not tel:
        return None
    digitos = "".join(c for c in tel if c.isdigit())
    if digitos.startswith("59199"):
        return None
    if len(digitos) == 8 and digitos[0] in ("6", "7"):
        return f"+591{digitos}"
    if len(digitos) == 11 and digitos.startswith("591") and digitos[3] in ("6", "7"):
        return f"+{digitos}"
    if len(digitos) > 8 and not digitos.startswith("591") and digitos[0] in ("6", "7"):
        return f"+591{digitos[:8]}"
    return None

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
