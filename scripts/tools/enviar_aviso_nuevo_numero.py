"""
Script para enviar notificación de cambio de número oficial a pacientes de Soldent.
Incluye pausas seguras anti-bloqueo (25-35s) y personalización de nombres.
"""
import time
import random
import httpx

# URL del backend en Render
API_URL = "https://soldent-agenda.onrender.com/api/enviar-mensaje"

# Mensaje oficial aprobado
PLANTILLA_MENSAJE = (
    "¡Hola, {nombre}! Esperamos que estés muy bien ✨\n\n"
    "Soy el asistente virtual de la Dra. Pamela Pinto Suárez en *SOLDENT - Soluciones Dentales*. 🦷🤖\n\n"
    "Te escribo para informarte que hemos actualizado nuestra línea oficial de WhatsApp para atención, consultas y agendamiento a este nuevo número 📲.\n\n"
    "Por favor, guárdame en tus contactos como:\n"
    "👉 *Bot_Soldent*\n\n"
    "Así podrás recibir tus recordatorios de citas y escribirnos con total comodidad cuando lo necesites.\n\n"
    "¡Seguimos a tu entera disposición para cuidar tu sonrisa! 🦷💙"
)

# Lista de pacientes reales (limpiando notas clínicas de los nombres)
PACIENTES = [
    {"nombre": "Adriana", "telefono": "+59177804070"},
    {"nombre": "Alejandro", "telefono": "+59176381561"},
    {"nombre": "Carlos Erick", "telefono": "+59178454684"},
    {"nombre": "Christopher", "telefono": "+59175592115"},
    {"nombre": "Cristian", "telefono": "+59171679127"},
    {"nombre": "Driana", "telefono": "+59176643330"},
    {"nombre": "Ericka", "telefono": "+59171144080"},
    {"nombre": "Estefanía", "telefono": "+59176008273"},
    {"nombre": "Gael", "telefono": "+59170838491"},
    {"nombre": "Joselin", "telefono": "+59170202899"},
    {"nombre": "Mariana", "telefono": "+59170083575"},
    {"nombre": "Nahuel", "telefono": "+59176690999"},
    {"nombre": "Nicolás", "telefono": "+59170277520"},
    {"nombre": "Richard Alarcón", "telefono": "+59178400962"},
    {"nombre": "Richard Soria", "telefono": "+59169083173"},
    {"nombre": "Rosi", "telefono": "+59171671477"},
    {"nombre": "Rubén", "telefono": "+59176671111"},
    {"nombre": "Sofía y Renata", "telefono": "+59175018362"},
    {"nombre": "Thais", "telefono": "+59169076024"},
    {"nombre": "Wilfredo", "telefono": "+59174966420"},
]

def enviar_mensaje(telefono: str, texto: str) -> bool:
    try:
        r = httpx.post(API_URL, json={"number": telefono, "text": texto}, timeout=15.0)
        return r.status_code == 200
    except Exception as e:
        print(f"Error al enviar a {telefono}: {e}")
        return False

def enviar_prueba(numero_prueba="+59170277520"):
    print(f"\n🧪 Enviando mensaje de PRUEBA a {numero_prueba}...")
    texto = PLANTILLA_MENSAJE.format(nombre="Nicolás")
    ok = enviar_mensaje(numero_prueba, texto)
    if ok:
        print("✅ ¡Mensaje de prueba enviado con éxito! Revisa tu WhatsApp.")
    else:
        print("❌ Error al enviar la prueba. Asegúrate de haber escaneado el nuevo QR en Render.")

def enviar_a_todos():
    print(f"\n🚀 Iniciando envío seguro a {len(PACIENTES)} pacientes...")
    print("Se aplicará una pausa aleatoria de 25 a 35 segundos entre cada mensaje.\n")
    
    for i, p in enumerate(PACIENTES, 1):
        nombre = p["nombre"]
        telefono = p["telefono"]
        texto = PLANTILLA_MENSAJE.format(nombre=nombre)
        
        print(f"[{i}/{len(PACIENTES)}] Enviando a {nombre} ({telefono})...")
        ok = enviar_mensaje(telefono, texto)
        
        if ok:
            print(f"   ✅ Enviado correctamente a {nombre}")
        else:
            print(f"   ⚠️ Falló el envío a {nombre}")
            
        if i < len(PACIENTES):
            pausa = random.randint(25, 35)
            print(f"   ⏳ Esperando {pausa} segundos (Anti-Ban Meta)...")
            time.sleep(pausa)
            
    print("\n🎉 ¡Proceso finalizado! Todos los mensajes fueron procesados.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--todos":
        enviar_a_todos()
    else:
        enviar_prueba()
