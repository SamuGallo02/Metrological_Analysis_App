' ==============================================================================
' Modulo di Avvio Silenzioso dell'Applicativo (GUI Launcher)
' ==============================================================================
' Esegue l'inizializzazione del punto d'ingresso Python (main.py) attraverso
' l'interprete headless (pythonw.exe), sopprimendo la finestra del terminale.
'
' Autore: Candidato Tesi
' ==============================================================================

Option Explicit

Dim objShell, objFSO, strScriptDir, strPythonPath, strMainPath

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Determinazione dinamica della directory radice del progetto
strScriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Definizione dei percorsi relativi per l'ambiente virtuale e l'entry-point
strPythonPath = strScriptDir & "\venv\Scripts\pythonw.exe"
strMainPath = strScriptDir & "\main.py"

' Impostazione della directory di lavoro corrente
objShell.CurrentDirectory = strScriptDir

' Verifica dell'esistenza dell'eseguibile Python e avvio del processo senza console (Window Style 0)
If objFSO.FileExists(strPythonPath) And objFSO.FileExists(strMainPath) Then
    objShell.Run """" & strPythonPath & """ """ & strMainPath & """", 0, False
Else
    MsgBox "Impossibile avviare l'applicazione:" & vbCrLf & _
           "Ambiente virtuale o file principale non trovato nella directory corrente.", _
           16, "Errore di Inizializzazione"
End If

Set objFSO = Nothing
Set objShell = Nothing