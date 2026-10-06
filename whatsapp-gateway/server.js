const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, Browsers } = require('@whiskeysockets/baileys');
const pino = require('pino');
const QRCode = require('qrcode');
let qrcodeTerminal = null;
try { qrcodeTerminal = require('qrcode-terminal'); } catch (e) {}

const express = require('express');

let cors = null;
try { cors = require('cors'); } catch (e) {}

const fs = require('fs');
const path = require('path');
const http = require('http');

const PORT = 8080;
const PYTHON_BOT_URL = 'http://127.0.0.1:5005/webhook';

process.on('uncaughtException', (err) => {
  console.error('⚠️ [Node uncaughtException]:', err.message);
});

process.on('unhandledRejection', (reason) => {
  console.error('⚠️ [Node unhandledRejection]:', reason);
});

const app = express();
if (cors) {
  app.use(cors());
} else {
  app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', '*');
    res.header('Access-Control-Allow-Methods', '*');
    if (req.method === 'OPTIONS') return res.sendStatus(200);
    next();
  });
}
app.use(express.json());

let sock = null;
let currentQR = null;
let currentQRImage = null;
let isConnected = false;
let userJid = null;

let defaultAuthDir = path.join(__dirname, 'auth_info_baileys');
try {
  // Solo usar /data si tenemos permisos reales de escritura (ej. volumen Docker en la nube)
  // En Android / Termux, /data existe en la raíz del sistema pero NO es escribible por el usuario
  if (fs.existsSync('/data')) {
    const testFile = '/data/.write_check_' + process.pid;
    fs.writeFileSync(testFile, 'ok');
    fs.unlinkSync(testFile);
    defaultAuthDir = '/data/auth_info_baileys';
  }
} catch (e) {
  defaultAuthDir = path.join(__dirname, 'auth_info_baileys');
}

const authPath = process.env.AUTH_DIR || defaultAuthDir;
if (!fs.existsSync(authPath)) {
  try { fs.mkdirSync(authPath, { recursive: true }); } catch (e) {}
}

// Utility to resolve an LID (@lid) to phone number (@s.whatsapp.net) using local Baileys session store
function resolveLidToPhone(jid) {
  if (!jid || typeof jid !== 'string') return jid;
  if (!jid.includes('@lid')) return jid;

  const lid = jid.split('@')[0].split(':')[0];
  const mappingFile = path.join(authPath, `lid-mapping-${lid}_reverse.json`);
  if (fs.existsSync(mappingFile)) {
    try {
      const phone = JSON.parse(fs.readFileSync(mappingFile, 'utf-8'));
      if (phone) {
        return `${phone}@s.whatsapp.net`;
      }
    } catch (e) {
      console.warn('Error reading lid mapping file:', e.message);
    }
  }
  return jid;
}

// Número oficial del Bot y Número de la Dra. Pamela
const BOT_PHONE_EXPECTED = '59162422577';
const DOCTORA_PHONE_FORBIDDEN = '59178472875';
let lastSecurityWarning = null;

const BACKEND_INTERNAL_URL = process.env.API_BACKEND_URL || 'https://soldent-agenda.onrender.com';

// Restaurar archivos de sesión desde Supabase al arrancar
async function restaurarSesionDesdeDB() {
  if (fs.existsSync(path.join(authPath, 'creds.json'))) {
    console.log('[WhatsApp Sync] Sesión local encontrada en disco. Saltando espera de BD.');
    return true;
  }
  for (let intento = 1; intento <= 3; intento++) {
    try {
      console.log(`[WhatsApp Sync] Verificando sesión guardada en Supabase (intento ${intento})...`);
      const resp = await fetch(`${BACKEND_INTERNAL_URL}/api/internal/baileys-session`);
      if (resp.ok) {
        const data = await resp.json();
        const keys = Object.keys(data);
        if (keys.length > 0) {
          if (!fs.existsSync(authPath)) fs.mkdirSync(authPath, { recursive: true });
          for (const k of keys) {
            const filePath = path.join(authPath, k);
            fs.writeFileSync(filePath, data[k], 'utf-8');
          }
          console.log(`[WhatsApp Sync] ✅ ¡Restaurados ${keys.length} archivos de sesión desde Supabase!`);
          return true;
        } else {
          console.log('[WhatsApp Sync] Base de datos vacía: no hay sesión previa guardada.');
          return false;
        }
      }
    } catch (e) {
      console.log(`[WhatsApp Sync] Aviso al conectar con backend (${e.message})`);
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  return false;
}

// Guardar archivo individual de sesión en Supabase
async function sincronizarArchivoADB(filename) {
  try {
    const filePath = path.join(authPath, filename);
    if (!fs.existsSync(filePath)) return;
    const content = fs.readFileSync(filePath, 'utf-8');
    const res = await fetch(`${BACKEND_INTERNAL_URL}/api/internal/baileys-session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: filename, value: content })
    });
    if (res.ok) {
      console.log(`[WhatsApp Sync] 🔑 Archivo clave '${filename}' respaldado exitosamente en Supabase.`);
    }
  } catch (e) {
    console.warn(`[WhatsApp Sync Error ${filename}]:`, e.message);
  }
}

// Sincronizar solo los archivos esenciales de sesión en Supabase para no saturar memoria
async function sincronizarDirectorioADB() {
  try {
    if (!fs.existsSync(authPath)) return;
    // 1. Asegurar siempre creds.json primero de forma individual
    await sincronizarArchivoADB('creds.json');

    // 2. Limpieza proactiva de memoria: si hay más de 40 pre-keys acumuladas, borrar las viejas
    const allFiles = fs.readdirSync(authPath);
    const preKeys = allFiles.filter(f => f.startsWith('pre-key-')).sort();
    if (preKeys.length > 40) {
      const toDelete = preKeys.slice(0, preKeys.length - 20);
      for (const oldKey of toDelete) {
        try { fs.unlinkSync(path.join(authPath, oldKey)); } catch (e) {}
      }
    }

    // 3. Respaldar solo archivos de sesión activos y esenciales
    const files = fs.readdirSync(authPath).filter(f => {
      if (!f.endsWith('.json') || f === 'creds.json') return false;
      return f.startsWith('session-') || f.startsWith('app-state-') || f.startsWith('sender-key-');
    });

    const CHUNK_SIZE = 25;
    for (let i = 0; i < files.length; i += CHUNK_SIZE) {
      const slice = files.slice(i, i + CHUNK_SIZE);
      const items = {};
      for (const file of slice) {
        try {
          items[file] = fs.readFileSync(path.join(authPath, file), 'utf-8');
        } catch (e) {}
      }
      if (Object.keys(items).length > 0) {
        await fetch(`${BACKEND_INTERNAL_URL}/api/internal/baileys-session/batch`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items })
        });
      }
    }
    console.log(`[WhatsApp Sync] ✅ Respaldo ligero completado (${files.length + 1} archivos esenciales).`);
  } catch (e) {
    console.warn('[WhatsApp Sync Error]:', e.message);
  }
}

// Limpiar sesión en Supabase al hacer /reset o logout
async function borrarSesionEnDB() {
  try {
    await fetch(`${BACKEND_INTERNAL_URL}/api/internal/baileys-session`, { method: 'DELETE' });
    console.log('[WhatsApp Sync] Sesión eliminada de Supabase.');
  } catch (e) {
    console.warn('[WhatsApp Sync Error al borrar sesión en DB]:', e.message);
  }
}

// HTML page for easy QR scanning from browser
function getHtmlPage() {
  if (isConnected) {
    const isBotCorrect = userJid && userJid.includes('62422577');
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Soldent WhatsApp Gateway</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui, sans-serif; background: #f8fafc; color: #1e293b; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }
    .card { background: white; padding: 32px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); text-align: center; max-width: 460px; width: 100%; border: 1px solid #e2e8f0; }
    .status { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 999px; background: #ecfdf5; color: #059669; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #10b981; }
    h1 { font-size: 20px; margin: 0 0 8px; color: #0f172a; }
    p { color: #64748b; font-size: 14px; line-height: 1.5; margin: 0; }
    .badge { margin-top: 14px; display: inline-block; background: #f1f5f9; padding: 6px 12px; border-radius: 8px; font-family: monospace; font-size: 13px; color: #334155; }
    .info-box { margin-top: 18px; padding: 12px; border-radius: 12px; font-size: 13px; text-align: left; }
    .info-box.ok { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; }
    .btn-reset { margin-top: 24px; display: inline-block; padding: 8px 16px; background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; border-radius: 8px; font-size: 13px; cursor: pointer; text-decoration: none; }
  </style>
</head>
<body>
  <div class="card">
    <div class="status"><span class="dot"></span> Conectado y Activo</div>
    <h1>WhatsApp Vinculado con Éxito</h1>
    <p>La pasarela de Soldent está respondiendo mensajes de WhatsApp en tiempo real con IA.</p>
    
    <div class="badge">${userJid || 'Dispositivo Vinculado'}</div>

    <div class="info-box ok">
      <b>🤖 Número del Bot:</b> +591 62422577<br>
      <b>👩‍⚕️ Celular de la Dra. Pamela:</b> +591 78472875 (Independiente / Libre del bot)
    </div>

    <div style="margin-top: 20px;">
      <a href="/reset" class="btn-reset" onclick="return confirm('¿Deseas desvincular y escanear un nuevo QR?')">Desvincular / Escanear nuevo QR</a>
    </div>
  </div>
</body>
</html>`;
  }

  if (currentQRImage) {
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Vincular WhatsApp - Soldent</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="5">
  <style>
    body { font-family: system-ui, sans-serif; background: #f0fdf4; color: #1e293b; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }
    .card { background: white; padding: 32px 24px; border-radius: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); text-align: center; max-width: 460px; width: 100%; border: 1px solid #bbf7d0; }
    .header { margin-bottom: 16px; }
    .badge { display: inline-block; padding: 4px 12px; border-radius: 999px; background: #dcfce7; color: #15803d; font-weight: 700; font-size: 12px; margin-bottom: 10px; text-transform: uppercase; }
    h1 { font-size: 20px; margin: 0 0 6px; color: #0f172a; }
    p { color: #64748b; font-size: 13px; line-height: 1.4; margin: 0; }
    .qr-container { padding: 14px; background: white; border: 2px dashed #86efac; border-radius: 16px; display: inline-block; margin: 16px 0; }
    img { width: 260px; height: 260px; display: block; }
    .alert-box { background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; padding: 12px; text-align: left; font-size: 12px; color: #991b1b; margin-bottom: 14px; line-height: 1.4; }
    .bot-box { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 12px; padding: 12px; text-align: left; font-size: 12px; color: #1e40af; margin-bottom: 14px; line-height: 1.4; }
    ol { text-align: left; font-size: 13px; color: #334155; line-height: 1.6; padding-left: 20px; margin: 16px 0 0; }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="badge">Soldent • Pasarela WhatsApp</div>
      <h1>Vincular Bot de WhatsApp</h1>
      <p>Escanea este código QR con el celular asignado para la atención automática</p>
    </div>

    ${lastSecurityWarning ? `<div class="alert-box"><b>⚠️ ALERTA DE SEGURIDAD:</b><br>${lastSecurityWarning}</div>` : ''}

    <div class="bot-box">
      <b style="font-size: 13px;">📱 Línea asignada al BOT:</b> Escanea con el WhatsApp oficial del consultorio.<br>
      Abre WhatsApp en el celular del bot y vincula este dispositivo.
    </div>

    <div class="alert-box">
      <b>⛔ NO ESCANEAR con el iPhone de la Dra. Pamela (78472875):</b><br>
      El número personal de la doctora no debe tener el bot vinculado para que pueda agendar y chatear libremente.
    </div>

    <div class="qr-container">
      <img src="${currentQRImage}" alt="Código QR WhatsApp" />
    </div>

    <ol>
      <li>En el celular del bot, abre WhatsApp.</li>
      <li>Toca <b>Menú (⋮)</b> o <b>Ajustes</b> > <b>Dispositivos vinculados</b>.</li>
      <li>Toca <b>Vincular un dispositivo</b> y apunta la cámara a este código QR.</li>
    </ol>
  </div>
</body>
</html>`;
  }

  return `<!DOCTYPE html><html><head><meta http-equiv="refresh" content="3"><title>Soldent - Generando QR</title><meta name="viewport" content="width=device-width, initial-scale=1"></head><body style="font-family: system-ui, sans-serif; background: #f8fafc; color: #1e293b; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px;">
    <div style="background: white; padding: 32px 24px; border-radius: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); text-align: center; max-width: 440px; width: 100%; border: 1px solid #e2e8f0;">
      <div style="font-size: 38px; margin-bottom: 12px;">⏳</div>
      <h2 style="font-size: 20px; margin: 0 0 8px; color: #0f172a;">Preparando Código QR...</h2>
      <p style="color: #64748b; font-size: 13px; line-height: 1.5; margin: 0 0 20px;">Conectando con la red de WhatsApp. Esta pantalla se actualiza automáticamente cada 3 segundos.</p>
      <div>
        <a href="/reset" style="display: inline-block; padding: 10px 18px; background: #fee2e2; color: #dc2626; border-radius: 12px; font-size: 13px; font-weight: 700; text-decoration: none; border: 1px solid #fca5a5;">
          🔄 Limpiar sesión y Forzar nuevo QR
        </a>
      </div>
    </div>
  </body></html>`;
}

app.get('/', (req, res) => {
  res.send(getHtmlPage());
});

app.get('/qr', (req, res) => {
  res.send(getHtmlPage());
});

app.get('/status', (req, res) => {
  res.json({
    connected: isConnected,
    user: userJid,
    hasQR: !!currentQR
  });
});

app.get('/reset', async (req, res) => {
  try {
    isConnected = false;
    currentQR = null;
    currentQRImage = null;
    userJid = null;
    if (sock) {
      try { sock.end(); } catch (e) {}
    }
    if (fs.existsSync(authPath)) {
      fs.rmSync(authPath, { recursive: true, force: true });
    }
    await borrarSesionEnDB();
    setTimeout(startBaileys, 1000);
    res.send('<p>Sesión reiniciada. <a href="/">Volver a escanear QR</a></p><script>setTimeout(() => location.href="/", 1500);</script>');
  } catch (err) {
    res.status(500).send('Error reiniciando sesión: ' + err.message);
  }
});

app.get('/reconnect', async (req, res) => {
  try {
    isConnected = false;
    currentQR = null;
    currentQRImage = null;
    if (sock) {
      try { sock.end(); } catch (e) {}
    }
    const restored = await restaurarSesionDesdeDB();
    setTimeout(startBaileys, 1000);
    res.json({ ok: true, restored });
  } catch (err) {
    res.status(500).json({ ok: false, error: err.message });
  }
});

// Evolution API compatibility & direct send endpoint
async function handleSendText(req, res) {
  try {
    const rawNumber = req.body.number || req.body.phone || req.body.to || req.body.target;
    const rawText = req.body.text !== undefined ? req.body.text : (req.body.message !== undefined ? req.body.message : '');
    const texto = (typeof rawText === 'string' ? rawText : String(rawText || '')).trim();

    if (!rawNumber || !texto) {
      return res.status(400).json({ error: 'Faltan parámetros: number y text/message válidos son requeridos' });
    }

    if (!sock || !isConnected) {
      return res.status(503).json({ error: 'WhatsApp no está conectado todavía. Por favor escanea el código QR en http://localhost:8080' });
    }

    let targetJid = rawNumber;

    // Handle @lid or @s.whatsapp.net or raw phone numbers
    if (typeof rawNumber === 'string' && (rawNumber.includes('@lid') || rawNumber.includes('@s.whatsapp.net'))) {
      targetJid = rawNumber;
    } else {
      const clean = String(rawNumber).replace(/\D/g, '');
      targetJid = `${clean}@s.whatsapp.net`;
    }

    // Simulación de presencia humana para evitar detección de bots por Meta
    try {
      await sock.sendPresenceUpdate('composing', targetJid);
      const typingDelay = Math.floor(Math.random() * 1500) + 1800; // 1.8s a 3.3s de tecleo natural
      await new Promise((r) => setTimeout(r, typingDelay));
      await sock.sendPresenceUpdate('paused', targetJid);
    } catch (e) {
      // Continuar con el envío si la presencia falla
    }

    await sock.sendMessage(targetJid, { text: texto });
    console.log(`[WhatsApp OUT] Mensaje enviado con éxito a ${targetJid}: ${texto.substring(0, 45)}...`);

    try {
      await sock.sendPresenceUpdate('available');
    } catch (e) {}
    res.json({ status: 'SUCCESS', message: 'Mensaje enviado correctamente', target: targetJid, text: texto });
  } catch (err) {
    console.error('[WhatsApp OUT Error]', err.message);
    res.status(500).json({ error: err.message });
  }
}

app.post('/message/sendText/:instance', handleSendText);
app.post('/send-message', handleSendText);

// Profile picture update endpoint (Evolution API compatibility)
async function handleUpdateProfilePicture(req, res) {
  try {
    if (!sock || !isConnected) {
      return res.status(503).json({ error: 'WhatsApp no está conectado todavía. Por favor escanea el código QR en http://localhost:8080' });
    }

    const { picture, number } = req.body;
    let imageBuffer = null;

    if (!picture) {
      const defaultPath = path.resolve(__dirname, '..', 'frontend', 'public', 'images', 'bot-perfil.jpg');
      if (fs.existsSync(defaultPath)) {
        imageBuffer = fs.readFileSync(defaultPath);
      } else {
        return res.status(400).json({ error: 'Parámetro picture es requerido' });
      }
    } else if (Buffer.isBuffer(picture)) {
      imageBuffer = picture;
    } else if (typeof picture === 'string') {
      if (picture.startsWith('data:image')) {
        const base64Data = picture.replace(/^data:image\/\w+;base64,/, '');
        imageBuffer = Buffer.from(base64Data, 'base64');
      } else if (picture.length > 500 && !picture.includes('\n') && !fs.existsSync(picture)) {
        imageBuffer = Buffer.from(picture, 'base64');
      } else if (fs.existsSync(picture)) {
        imageBuffer = fs.readFileSync(picture);
      } else {
        const resolved = path.resolve(process.cwd(), picture);
        if (fs.existsSync(resolved)) {
          imageBuffer = fs.readFileSync(resolved);
        } else {
          const projResolved = path.resolve(__dirname, '..', picture);
          if (fs.existsSync(projResolved)) {
            imageBuffer = fs.readFileSync(projResolved);
          } else {
            return res.status(400).json({ error: `No se encontró el archivo de imagen en: ${picture}` });
          }
        }
      }
    }

    const targetJid = number ? (number.includes('@') ? number : `${number.replace(/\D/g, '')}@s.whatsapp.net`) : sock.user.id;
    console.log(`[WhatsApp Profile] Actualizando foto de perfil para ${targetJid}...`);

    await sock.updateProfilePicture(targetJid, imageBuffer);
    console.log(`[WhatsApp Profile] Foto de perfil actualizada con éxito para ${targetJid}!`);

    res.json({
      status: 'SUCCESS',
      message: 'Foto de perfil actualizada correctamente',
      target: targetJid
    });
  } catch (err) {
    console.error('[WhatsApp Profile Error]', err.message);
    res.status(500).json({ error: err.message });
  }
}

app.post('/chat/updateProfilePicture/:instance', handleUpdateProfilePicture);
app.post('/chat/updateProfilePicture', handleUpdateProfilePicture);
app.post('/instance/updateProfilePicture/:instance', handleUpdateProfilePicture);
app.post('/instance/updateProfilePicture', handleUpdateProfilePicture);

async function startBaileys() {
  try {
    await restaurarSesionDesdeDB();

    const { state, saveCreds } = await useMultiFileAuthState(authPath);

    sock = makeWASocket({
      auth: state,
      printQRInTerminal: false,
      logger: pino({ level: 'silent' }),
      browser: Browsers.macOS('Desktop'),
      syncFullHistory: false,
      defaultQueryTimeoutMs: 60000,
      connectTimeoutMs: 60000,
      keepAliveIntervalMs: 30000,
      generateHighQualityLinkPreview: false
    });

    sock.ev.on('creds.update', async () => {
      await saveCreds();
      await sincronizarArchivoADB('creds.json');
    });

    sock.ev.on('connection.update', async (update) => {
      const { connection, lastDisconnect, qr } = update;

      if (qr) {
        currentQR = qr;
        isConnected = false;
        try {
          currentQRImage = await QRCode.toDataURL(qr);
          const rootDir = path.resolve(__dirname, '..');
          await QRCode.toFile(path.join(rootDir, 'whatsapp-qr.png'), qr, { width: 400 });
          fs.writeFileSync(path.join(rootDir, 'whatsapp-qr.html'), getHtmlPage(), 'utf-8');
        } catch (e) {
          console.error('Error generando QR image:', e.message);
        }

        console.log('\n' + '='.repeat(60));
        console.log('📌 [WHATSAPP QR CODE GENERADO] Escanea este código:');
        if (qrcodeTerminal) {
          try { qrcodeTerminal.generate(qr, { small: true }); } catch (e) {}
        }
        console.log('\n💡 También puedes abrir en tu navegador: http://localhost:8080');
        console.log('='.repeat(60) + '\n');
      }

      if (connection === 'close') {
        isConnected = false;
        const statusCode = (lastDisconnect?.error)?.output?.statusCode;
        const isLoggedOut = statusCode === DisconnectReason.loggedOut;

        console.log(`[WhatsApp] Conexión cerrada (código: ${statusCode || 'n/a'}). ¿Cierre de sesión manual (loggedOut)?: ${isLoggedOut}`);

        if (isLoggedOut) {
          console.log('[WhatsApp] El usuario cerró sesión en su teléfono (loggedOut 401). Limpiando para nuevo QR...');
          currentQR = null;
          currentQRImage = null;
          await borrarSesionEnDB();
          try {
            if (fs.existsSync(authPath)) {
              fs.rmSync(authPath, { recursive: true, force: true });
            }
          } catch (e) {
            console.error('Error limpiando auth_info_baileys:', e.message);
          }
          setTimeout(startBaileys, 2000);
        } else {
          // Para cualquier otro código (428 connectionClosed, 408 timedOut, 440 replaced, 515 restart):
          // RECONECTAR manteniendo la sesión intacta en Supabase y disco
          console.log(`[WhatsApp] Reconectando automáticamente a WhatsApp en 3s sin perder sesión (código: ${statusCode})...`);
          setTimeout(startBaileys, 3000);
        }
      } else if (connection === 'open') {
        isConnected = true;
        currentQR = null;
        currentQRImage = null;
        userJid = sock.user?.id || 'Conectado';
        const cleanUserPhone = String(userJid).split('@')[0].split(':')[0].replace(/\D/g, '');
        console.log('\n' + '='.repeat(60));
        console.log('✅ [WHATSAPP CONECTADO!] Dispositivo vinculado con éxito.');
        console.log(`Usuario: ${userJid} (Teléfono detectado: ${cleanUserPhone})`);
        console.log('='.repeat(60) + '\n');

        // SEGURIDAD CRÍTICA: Bloquear e impedir que el bot se vincule al número personal de la Dra. Pamela (78472875)
        if (cleanUserPhone.includes('78472875')) {
          console.error('\n🚨 [SEGURIDAD SOLDENT] ¡ERROR CRÍTICO!');
          console.error('🚨 Se escaneó el QR con el número personal de la Dra. Pamela (+591 78472875).');
          console.error('🚨 Desvinculando inmediatamente para proteger su WhatsApp personal y agenda...\n');
          await borrarSesionEnDB();
          try {
            sock.logout();
          } catch (e) {}
          if (fs.existsSync(authPath)) {
            fs.rmSync(authPath, { recursive: true, force: true });
          }
          isConnected = false;
          userJid = null;
          lastSecurityWarning = '⛔ ATENCIÓN: Se intentó vincular el número personal de la Dra. Pamela (+591 78472875). Por seguridad, la vinculación fue cancelada de inmediato. Por favor escanea este código QR ÚNICAMENTE con el celular del bot (+591 62422577).';
          setTimeout(startBaileys, 3000);
          return;
        }

        // Sincronizar sesión completa inmediatamente a Supabase
        await sincronizarDirectorioADB();

        lastSecurityWarning = null;

        const rootDir = path.resolve(__dirname, '..');
        fs.writeFileSync(path.join(rootDir, 'whatsapp-qr.html'), getHtmlPage(), 'utf-8');

        // Automatic profile picture update on connection
        try {
          const profilePicPath = path.resolve(rootDir, 'frontend', 'public', 'images', 'bot-perfil.jpg');
          if (fs.existsSync(profilePicPath)) {
            console.log('[WhatsApp Profile] Aplicando foto de perfil oficial (bot-perfil.jpg)...');
            const picBuffer = fs.readFileSync(profilePicPath);
            sock.updateProfilePicture(sock.user.id, picBuffer)
              .then(() => console.log('✅ Foto de perfil fijada con éxito en WhatsApp!'))
              .catch(err => console.warn('Aviso actualizando foto de perfil:', err.message));
          }
        } catch (e) {
          console.warn('Error al verificar bot-perfil.jpg:', e.message);
        }
      }
    });

    // Handle incoming messages
    sock.ev.on('messages.upsert', async ({ messages, type }) => {
      for (const msg of messages) {
        if (!msg.message || msg.key.fromMe) continue;

        const remoteJid = msg.key.remoteJid;
        if (!remoteJid || remoteJid.includes('@g.us') || remoteJid === 'status@broadcast') continue;

        const pushName = msg.pushName || 'Paciente';
        const text = msg.message.conversation || msg.message.extendedTextMessage?.text || '';

        if (!text.trim()) continue;

        // Descartar mensajes extremadamente antiguos (> 10 minutos)
        const msgTimestamp = Number(msg.messageTimestamp || 0);
        const nowSec = Math.floor(Date.now() / 1000);
        if (msgTimestamp > 0 && (nowSec - msgTimestamp) > 600) {
          console.log(`[WhatsApp IN] Descartando mensaje muy antiguo (${nowSec - msgTimestamp}s de antigüedad): "${text.slice(0, 35)}..."`);
          continue;
        }

        // Resolve real phone if it is an LID
        const resolvedPhone = remoteJid.includes('@lid') ? resolveLidToPhone(remoteJid) : remoteJid;

        // Detección de la Dra. Pamela (78472875)
        const isDoctor = remoteJid.includes('78472875') || (resolvedPhone && resolvedPhone.includes('78472875'));
        if (isDoctor) {
          console.log(`[WhatsApp IN] 👩‍⚕️ Mensaje de la Dra. Pamela (+591 78472875) recibido: "${text.slice(0, 45)}" -> Asistente Personal.`);
        } else {
          console.log(`[WhatsApp IN] De ${pushName} (${remoteJid} -> ${resolvedPhone}): ${text}`);
        }

        // Forward to Python bot (asynchronously via HTTP POST)
        try {
          const payload = JSON.stringify({
            from: remoteJid,
            resolvedPhone: resolvedPhone,
            phone: (resolvedPhone || remoteJid).replace('@s.whatsapp.net', '').replace('@lid', '').replace(/\D/g, ''),
            name: isDoctor ? 'Dra. Pamela Pinto Suárez' : pushName,
            isDoctor: isDoctor,
            text: text
          });

          const req = http.request(PYTHON_BOT_URL, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Content-Length': Buffer.byteLength(payload)
            }
          });
          req.on('error', (e) => {
            console.log('[Forward to Bot] Bot no disponible aún en', PYTHON_BOT_URL);
          });
          req.write(payload);
          req.end();
        } catch (err) {
          console.error('Error forwarding message to Python bot:', err.message);
        }
      }
    });
  } catch (err) {
    console.error('Error en startBaileys:', err.message);
    setTimeout(startBaileys, 3000);
  }
}

// Respaldo periódico a Supabase cada 5 minutos si la sesión está conectada
setInterval(() => {
  if (isConnected) {
    sincronizarDirectorioADB().catch(() => {});
  }
}, 5 * 60 * 1000);

// Anti-Sleep Render Keep-Alive: Ping cada 7 minutos para evitar que Render se duerma
setInterval(() => {
  fetch('https://soldent-agenda.onrender.com/api/salud')
    .then(() => console.log('⚡ [Keep-Alive Node] Ping enviado a Render (24/7 activo)'))
    .catch((err) => console.log('⚠️ [Keep-Alive Node Error]:', err.message));
}, 7 * 60 * 1000);

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[Soldent WhatsApp Gateway] Servidor HTTP escuchando en http://localhost:${PORT}`);
  startBaileys();
});
