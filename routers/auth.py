from fastapi import APIRouter, Depends, HTTPException, status
from config import settings
from schemas import PinLoginIn
from security import generar_auth_token, verificar_autenticacion

router = APIRouter(prefix="/api/auth", tags=["Autenticación"])

@router.post("/pin")
def login_pin(data: PinLoginIn):
    pin_limpio = data.pin.strip() if data.pin else ""
    if pin_limpio != settings.DOCTORA_PIN:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="PIN de acceso incorrecto. Por favor verifica e intenta de nuevo."
        )
    token = generar_auth_token()
    return {
        "ok": True,
        "token": token,
        "usuario": "Dra. Pamela Pinto Suárez",
        "mensaje": "Acceso autorizado"
    }

@router.get("/verificar")
def verificar_sesion(_auth: bool = Depends(verificar_autenticacion)):
    return {
        "ok": True,
        "valido": True,
        "usuario": "Dra. Pamela Pinto Suárez"
    }
