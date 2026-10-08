import os, json, re
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/calendar.events']

def actualizar_env(key: str, valor: str):
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = rf'^{key}=.*$'
    if re.search(pattern, content, flags=re.MULTILINE):
        new_content = re.sub(pattern, f'{key}={valor}', content, flags=re.MULTILINE)
    else:
        new_content = content + f'\n{key}={valor}'
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

def main():
    if not os.path.exists('credentials.json'):
        print("Error: No se encontro 'credentials.json'.")
        print("Asegurate de descargarlo desde Google Cloud Console > APIs & Services > Credentials > OAuth 2.0 Client IDs (Tipo: Desktop app).")
        return

    with open('credentials.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    top_key = list(data.keys())[0]
    client_id = data[top_key].get('client_id', '')
    client_secret = data[top_key].get('client_secret', '')

    if client_id:
        actualizar_env('GOOGLE_CLIENT_ID', client_id)
        print("[OK] GOOGLE_CLIENT_ID actualizado en .env")
    if client_secret:
        actualizar_env('GOOGLE_CLIENT_SECRET', client_secret)
        print("[OK] GOOGLE_CLIENT_SECRET actualizado en .env")

    print("\nIniciando flujo de autorizacion de Google Calendar en el navegador...")
    print("Abre el enlace que aparezca a continuacion si el navegador no se abre de forma automatica.")
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=8080, prompt='consent', access_type='offline')
    
    if creds.refresh_token:
        actualizar_env('GOOGLE_REFRESH_TOKEN', creds.refresh_token)
        print("\n" + "="*60)
        print("[EXITO] Se guardo automaticamente en tu archivo .env:")
        print(f"GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
        print("="*60)
    else:
        print("\n[AVISO] No se obtuvo refresh_token nuevo. Si necesitas forzar uno nuevo, ve a https://myaccount.google.com/permissions y revoca el acceso de la app antes de volver a ejecutar.")

if __name__ == '__main__':
    main()