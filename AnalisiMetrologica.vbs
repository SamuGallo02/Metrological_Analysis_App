' ==============================================================================
' Avvio dell'applicativo (Windows)
' ==============================================================================
' Nessun controllo di dipendenze ad ogni avvio: l'installazione si fa una volta
' sola con "Installa_Windows.vbs" (registra l'esito in .install_state.json).
' Se l'app non risulta installata, propone di lanciare l'installer.
' Crea inoltre, al primo avvio, il collegamento con icona sul Desktop.
'
' Autore: Samuele Gallo
' ==============================================================================

Option Explicit

Dim objShell, objFSO, strScriptDir, strVenvPythonw, strMainPath
Dim strIconPath, strShortcutPath, objShortcut, blnInstalled, intAnswer

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strScriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
objShell.CurrentDirectory = strScriptDir

strIconPath = strScriptDir & "\assets\app_icon.ico"
strShortcutPath = objShell.SpecialFolders("Desktop") & "\Analisi Metrologica.lnk"

If Not objFSO.FileExists(strShortcutPath) Then
    Set objShortcut = objShell.CreateShortcut(strShortcutPath)
    objShortcut.TargetPath = WScript.ScriptFullName
    objShortcut.WorkingDirectory = strScriptDir
    If objFSO.FileExists(strIconPath) Then objShortcut.IconLocation = strIconPath
    objShortcut.Description = "Stereo Metrology Analysis"
    objShortcut.Save
End If

strVenvPythonw = strScriptDir & "\venv\Scripts\pythonw.exe"
strMainPath = strScriptDir & "\main.py"

If Not objFSO.FileExists(strMainPath) Then
    MsgBox "main.py non trovato in:" & vbCrLf & strScriptDir & vbCrLf & vbCrLf & _
           "Controlla di aver scaricato l'intera cartella del progetto.", 16, "Errore di Inizializzazione"
    WScript.Quit 1
End If

' Installato = stato scritto dall'installer (o, per installazioni precedenti, il vecchio marcatore)
blnInstalled = objFSO.FileExists(strVenvPythonw) And _
               (objFSO.FileExists(strScriptDir & "\.install_state.json") Or objFSO.FileExists(strScriptDir & "\venv\.setup_complete"))

If Not blnInstalled Then
    intAnswer = MsgBox("L'applicativo non e' ancora installato su questo computer." & vbCrLf & vbCrLf & _
                       "Avviare ora l'installazione?", 36, "Installazione necessaria")
    If intAnswer <> 6 Then WScript.Quit 0
    objShell.Run """" & strScriptDir & "\Installa_Windows.vbs""", 1, True
    If Not objFSO.FileExists(strScriptDir & "\.install_state.json") Then WScript.Quit 1
End If

objShell.Run """" & strVenvPythonw & """ """ & strMainPath & """", 0, False

Set objFSO = Nothing
Set objShell = Nothing
