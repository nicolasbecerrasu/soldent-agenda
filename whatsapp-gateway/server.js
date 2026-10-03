const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys');
const pino = require('pino');
const QRCode = require('qrcode');
const qrcodeTerminal = require('qrcode-terminal');
const express = require('express');
const cors = require('cors');
const fs = require('fs');
const path = require('path');
const http = require('http');

const PORT = 8080;
const PYTHON_BOT_URL = 'http://127.0.0.1:5005/webhook';

const app = express();
app.use(cors());
app.use(express.json());

let sock = null;
let currentQR = null;
let currentQRImage = null;
let isConnected = false;
let userJid = null;

const defaultAuthDir = fs.existsSync('/data') ? '/data/auth_info_baileys' : path.join(__dirname, 'auth_info_baileys');
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

// HTML page for easy QR scanning from browser
function getHtmlPage() {
  if (isConnected) {
    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Soldent WhatsApp Gateway</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: system-ui, sans-serif; background: #f8fafc; color: #1e293b; display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; padding: 20px; }
    .card { background: white; padding: 32px; border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.05); text-align: center; max-width: 440px; width: 100%; border: 1px solid #e2e8f0; }
    .status { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border-radius: 999px; background: #ecfdf5; color: #059669; font-weight: 600; font-size: 14px; margin-bottom: 16px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #10b981; }
    h1 { font-size: 20px; margin: 0 0 8px; color: #0f172a; }
    p { color: #64748b; font-size: 14px; line-height: 1.5; margin: 0; }
    .badge { margin-top: 16px; display: inline-block; background: #f1f5f9; padding: 6px 12px; border-radius: 8px; font-family: monospace; font-size: 13px; color: #334155; }
    .btn-reset { margin-top: 24px; display: inline-block; padding: 8px 16px; background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; border-radius: 8px; font-size: 13px; cursor: pointer; text-decoration: none; }
  </style>
</head>
<body>
  <div class="card">
    <div class="status"><span class="dot"></span> Conectado y Activo</div>
    <h1>WhatsApp Vinculado con Éxito</h1>
    <p>La pasarela de Soldent está respondiendo mensajes de WhatsApp en tiempo real con Google Gemini.</p>
    <div class="badge">${userJid || 'Dispositivo Vinculado'}</div>
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
    .card { background: white; padding: 32px; border-radius: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); text-align: center; max-width: 440px; width: 100%; border: 1px solid #bbf7d0; }
    .header { margin-bottom: 20px; }
    .badge { display: inline-block; padding: 4px 12px; border-radius: 999px; background: #dcfce7; color: #15803d; font-weight: 700; font-size: 12px; margin-bottom: 10px; text-transform: uppercase; }
    h1 { font-size: 20px; margin: 0 0 6px; color: #0f172a; }
    p { color: #64748b; font-size: 13px; line-height: 1.4; margin: 0; }
    .qr-container { padding: 16px; background: white; border: 2px dashed #86efac; border-radius: 16px; display: inline-block; margin: 20px 0; }
    img { width: 280px; height: 280px; display: block; }
    ol { text-align: left; font-size: 13px; color: #334155; line-height: 1.6; padding-left: 20px; margin: 16px 0 0; }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="badge">Soldent • Pasarela WhatsApp</div>
      <h1>Escanea el Código QR</h1>
      <p>Vincula el WhatsApp de Soldent desde tu celular Android secundario</p>
    </div>
    <div class="qr-container">
      <img src="${currentQRImage}" alt="Código QR WhatsApp" />
    </div>
    <ol>
      <li>Abre WhatsApp en tu celular secundario.</li>
      <li>Toca <b>Menú (⋮)</b> o <b>Ajustes</b> > <b>Dispositivos vinculados</b>.</li>
      <li>Toca <b>Vincular un dispositivo</b> y apunta la cámara a este código QR.</li>
    </ol>
  </div>
</body>
</html>`;
  }

  return `<!DOCTYPE html><html><head><meta http-equiv="refresh" content="2"></head><body style="font-family: sans-serif; text-align: center; padding-top: 50px;">Generando código QR... por favor espera unos segundos.</body></html>`;
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

app.get('/reset', (req, res) => {
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
    setTimeout(startBaileys, 1000);
    res.send('<p>Sesión reiniciada. <a href="/">Volver a escanear QR</a></p><script>setTimeout(() => location.href="/", 1500);</script>');
  } catch (err) {
    res.status(500).send('Error reiniciando sesión: ' + err.message);
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

    await sock.sendMessage(targetJid, { text: texto });
    console.log(`[WhatsApp OUT] Mensaje enviado con éxito a ${targetJid}: ${texto.substring(0, 45)}...`);
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
    const { state, saveCreds } = await useMultiFileAuthState(authPath);

    sock = makeWASocket({
      auth: state,
      printQRInTerminal: false,
      logger: pino({ level: 'silent' }),
      browser: ['Soldent Bot', 'Chrome', '1.0.0']
    });

    sock.ev.on('creds.update', saveCreds);

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
        console.log('='.repeat(60) + '\n');
        qrcodeTerminal.generate(qr, { small: true });
        console.log('\n💡 También puedes abrir en tu navegador: http://localhost:8080');
        console.log('='.repeat(60) + '\n');
      }

      if (connection === 'close') {
        isConnected = false;
        const statusCode = (lastDisconnect?.error)?.output?.statusCode;
        const isLoggedOut = statusCode === DisconnectReason.loggedOut;

        console.log(`[WhatsApp] Conexión cerrada (código: ${statusCode || 'n/a'}). ¿Sesión cerrada/logout?: ${isLoggedOut}`);

        if (isLoggedOut) {
          console.log('[WhatsApp] Limpiando credenciales antiguas para generar nuevo QR...');
          try {
            if (fs.existsSync(authPath)) {
              fs.rmSync(authPath, { recursive: true, force: true });
            }
          } catch (e) {
            console.error('Error limpiando auth_info_baileys:', e.message);
          }
          setTimeout(startBaileys, 2000);
        } else {
          // Reintento de reconexión por pérdida momentánea de red
          setTimeout(startBaileys, 3000);
        }
      } else if (connection === 'open') {
        isConnected = true;
        currentQR = null;
        currentQRImage = null;
        userJid = sock.user?.id || 'Conectado';
        console.log('\n' + '='.repeat(60));
        console.log('✅ [WHATSAPP CONECTADO!] Dispositivo vinculado con éxito.');
        console.log(`Usuario: ${userJid}`);
        console.log('='.repeat(60) + '\n');

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
      if (type !== 'notify') return;

      for (const msg of messages) {
        if (!msg.message || msg.key.fromMe) continue;

        const remoteJid = msg.key.remoteJid;
        if (!remoteJid || remoteJid.includes('@g.us') || remoteJid === 'status@broadcast') continue;

        const pushName = msg.pushName || 'Paciente';
        const text = msg.message.conversation || msg.message.extendedTextMessage?.text || '';

        if (!text.trim()) continue;

        // Descartar mensajes viejos recibidos al reconectar o sincronizar historial (> 180 segundos)
        const msgTimestamp = Number(msg.messageTimestamp || 0);
        const nowSec = Math.floor(Date.now() / 1000);
        if (msgTimestamp > 0 && (nowSec - msgTimestamp) > 180) {
          console.log(`[WhatsApp IN] Descartando mensaje antiguo (${nowSec - msgTimestamp}s de antigüedad): "${text.slice(0, 35)}..."`);
          continue;
        }

        // Resolve real phone if it is an LID
        const resolvedPhone = remoteJid.includes('@lid') ? resolveLidToPhone(remoteJid) : remoteJid;
        console.log(`[WhatsApp IN] De ${pushName} (${remoteJid} -> ${resolvedPhone}): ${text}`);

        // Forward to Python bot (asynchronously via HTTP POST)
        try {
          const payload = JSON.stringify({
            from: remoteJid,
            resolvedPhone: resolvedPhone,
            phone: (resolvedPhone || remoteJid).replace('@s.whatsapp.net', '').replace('@lid', '').replace(/\D/g, ''),
            name: pushName,
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

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[Soldent WhatsApp Gateway] Servidor HTTP escuchando en http://localhost:${PORT}`);
  startBaileys();
});
