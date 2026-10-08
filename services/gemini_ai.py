import httpx
from typing import Optional
from config import settings

def safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass

def llamar_gemini_http(prompt_sistema: str, historial: list) -> Optional[str]:
    """Invoca la API de Gemini mediante llamadas HTTP directas y ligeras (sin SDKs pesados)."""
    if not settings.GEMINI_API_KEY:
        return None

    modelos = [
        "gemini-3.5-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-3.8-flash"
    ]

    contents = []
    for item in historial:
        contents.append({
            "role": item["role"],
            "parts": [{"text": item["text"]}]
        })

    payload = {
        "system_instruction": {
            "parts": [{"text": prompt_sistema}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 600
        }
    }

    for modelo in modelos:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={settings.GEMINI_API_KEY}"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    cands = data.get("candidates", [])
                    if cands:
                        parts = cands[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"].strip()
                elif resp.status_code in (404, 400):
                    continue
        except Exception as e:
            safe_print(f"[Gemini HTTP con {modelo}]: {e}")
            continue

    return None
