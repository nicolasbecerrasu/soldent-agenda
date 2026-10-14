import os
import sys
import re
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# Asegurar que el directorio raíz del proyecto esté en sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE_DIR)

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from config import settings

SCOPES = 'https://www.googleapis.com/auth/calendar.events'
REDIRECT_URI = 'http://localhost:8080/'

captured_token = None

class OAuthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silenciar logs default
        pass

    def do_GET(self):
        global captured_token
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)

        if 'code' in query:
            code = query['code'][0]
            print(f"\n[OK] Código de autorización recibido de Google.")
            
            # Canjear el código por tokens
            token_url = "https://oauth2.googleapis.com/token"
            data = {
                'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': REDIRECT_URI
            }
            res = requests.post(token_url, data=data)
            tokens = res.json()

            if 'refresh_token' in tokens:
                captured_token = tokens['refresh_token']
                html = """
                <html>
                <body style="font-family: Arial; text-align: center; padding-top: 50px;">
                    <h1 style="color: #10B981;">&#10004; &#161;Autorizaci&oacute;n Exitosa!</h1>
                    <p style="font-size: 18px;">El nuevo token de Google Calendar se ha generado y guardado correctamente.</p>
                    <p style="color: #6B7280;">Ya puedes cerrar esta pesta&ntilde;a y volver al chat.</p>
                </body>
                </html>
                """
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(html.encode('utf-8'))
            else:
                error_msg = tokens.get('error_description', str(tokens))
                print(f"[ALERTA] Respuesta de Google sin refresh_token: {tokens}")
                html = f"""
                <html>
                <body style="font-family: Arial; text-align: center; padding-top: 50px;">
                    <h1 style="color: #EF4444;">Aviso</h1>
                    <p>Google respondi&oacute; pero no envi&oacute; un nuevo refresh_token ({error_msg}).</p>
                    <p>Acceso temporal obtenido: {tokens.get('access_token', 'No')[:15]}...</p>
                </body>
                </html>
                """
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(html.encode('utf-8'))
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No code parameter found in callback")

def actualizar_env_file(ruta_env: str, key: str, valor: str):
    if not os.path.exists(ruta_env):
        return
    with open(ruta_env, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = rf'^{key}=.*$'
    if re.search(pattern, content, flags=re.MULTILINE):
        new_content = re.sub(pattern, f'{key}={valor}', content, flags=re.MULTILINE)
    else:
        new_content = content + f'\n{key}={valor}'
    with open(ruta_env, 'w', encoding='utf-8') as f:
        f.write(new_content)

def main():
    print("=" * 65)
    print("SOLDENT - SERVIDOR OAUTH PARA RENOVAR GOOGLE CALENDAR")
    print("=" * 65)

    client_id = settings.GOOGLE_CLIENT_ID
    client_secret = settings.GOOGLE_CLIENT_SECRET

    if not client_id or not client_secret:
        print("Error: GOOGLE_CLIENT_ID o GOOGLE_CLIENT_SECRET no configurados.")
        return

    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={urllib.parse.quote(client_id)}&"
        f"redirect_uri={urllib.parse.quote(REDIRECT_URI)}&"
        f"response_type=code&"
        f"scope={urllib.parse.quote(SCOPES)}&"
        f"access_type=offline&"
        f"prompt=consent"
    )

    server = HTTPServer(('127.0.0.1', 8080), OAuthHandler)
    print("\nServidor escuchando en http://127.0.0.1:8080/")
    print(f"\nURL de autorizacion:\n{auth_url}\n")
    print("Esperando que el usuario autorice en el navegador...")

    # Atender 1 petición (el callback de Google)
    while not captured_token:
        server.handle_request()

    # Guardar en .env local
    env_local = os.path.join(BASE_DIR, '.env')
    actualizar_env_file(env_local, 'GOOGLE_REFRESH_TOKEN', captured_token)

    print("\n" + "=" * 65)
    print("NUEVO GOOGLE_REFRESH_TOKEN GENERADO:")
    print(captured_token)
    print("=" * 65)
    print("Guardado exitosamente en .env local.")

if __name__ == '__main__':
    main()
