' ==============================================================================
' Application launcher (Windows)
' ==============================================================================
' No dependency check at every launch: installation is done only once
' with the installer downloadable from the website (it records the result in librery\.install_state.json).
' If the app is not installed, it offers to launch the installer.
' It also creates, at first launch, the shortcut with icon on the Desktop.
'
' Autore: Samuele Gallo
' ==============================================================================

Option Explicit

Dim objShell, objFSO, strScriptDir, strVenvPythonw, strMainPath
Dim strIconPath, strShortcutPath, objShortcut, blnInstalled, intAnswer

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strScriptDir = objFSO.GetParentFolderName(objFSO.GetParentFolderName(objFSO.GetParentFolderName(WScript.ScriptFullName))) ' project root (this file lives in common\launchers\)
objShell.CurrentDirectory = strScriptDir

strIconPath = strScriptDir & "\common\assets\app_icon.ico"
strShortcutPath = objShell.SpecialFolders("Desktop") & "\Analisi Metrologica.lnk"

If True Then ' always recreated: so it follows any move of the file
    Set objShortcut = objShell.CreateShortcut(strShortcutPath)
    objShortcut.TargetPath = WScript.ScriptFullName
    objShortcut.WorkingDirectory = strScriptDir
    If objFSO.FileExists(strIconPath) Then objShortcut.IconLocation = strIconPath
    objShortcut.Description = "Stereo Metrology Analysis"
    objShortcut.Save
End If

strVenvPythonw = strScriptDir & "\librery\venv\Scripts\pythonw.exe"
strMainPath = strScriptDir & "\main.py"

If Not objFSO.FileExists(strMainPath) Then
    MsgBox "main.py non trovato in:" & vbCrLf & strScriptDir & vbCrLf & vbCrLf & _
           "Controlla di aver scaricato l'intera cartella del progetto.", 16, "Errore di Inizializzazione"
    WScript.Quit 1
End If

' Installed = state written by the installer (or, for earlier installations, the old marker)
blnInstalled = objFSO.FileExists(strVenvPythonw) And _
               (objFSO.FileExists(strScriptDir & "\librery\.install_state.json") Or objFSO.FileExists(strScriptDir & "\librery\venv\.setup_complete"))

If Not blnInstalled Then
    intAnswer = MsgBox("L'applicativo non e' ancora installato su questo computer." & vbCrLf & vbCrLf & _
                       "Aprire la pagina da cui scaricare l'installer?", 36, "Installazione necessaria")
    If intAnswer = 6 Then objShell.Run "https://samugallo02.github.io/Nautilus_Website/"
    WScript.Quit 0
End If

objShell.Run """" & strVenvPythonw & """ """ & strMainPath & """", 0, False

Set objFSO = Nothing
Set objShell = Nothing
