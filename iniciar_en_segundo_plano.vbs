Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)

' 1. Iniciar Pasarela WhatsApp (Node) completamente invisible (0 = ventana oculta)
WshShell.Run "cmd /c cd /d """ & strDir & "\whatsapp-gateway"" && node server.js", 0, False

WScript.Sleep 3000

' 2. Iniciar Asistente IA (Python) completamente invisible (0 = ventana oculta)
WshShell.Run "cmd /c cd /d """ & strDir & """ && python whatsapp_bot.py", 0, False

MsgBox "¡El Asistente de WhatsApp de Soldent ya esta ACTIVO!" & vbCrLf & vbCrLf & "Esta funcionando en segundo plano de forma 100% invisible, sin ventanas negras molestando." & vbCrLf & vbCrLf & "Para apagarlo cuando quieras, haz doble clic en 'detener_bot.bat'.", 64, "Soldent - Bot en Segundo Plano"
