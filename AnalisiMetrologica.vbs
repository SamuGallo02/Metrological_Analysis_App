' ==============================================================================
' Modulo di Avvio Silenzioso dell'Applicativo (GUI Launcher)
' ==============================================================================
' Esegue l'inizializzazione del punto d'ingresso Python (main.py) attraverso
' l'interprete headless (pythonw.exe), sopprimendo la finestra del terminale.
'
' Al primo avvio crea automaticamente un collegamento con l'icona
' dell'applicativo sul Desktop ("Analisi Metrologica.lnk"): un file .vbs non
' puo' avere un'icona propria in Windows (mostra sempre l'icona generica di
' sistema), solo un collegamento .lnk puo' averla. Dalle volte successive si
' puo' usare direttamente quel collegamento.
'
' Ordine di ricerca dell'interprete Python:
'   1. venv\Scripts\pythonw.exe del progetto (preferito)
'   2. pythonw.exe di sistema, se raggiungibile dal PATH
'   3. python.exe di sistema, se raggiungibile dal PATH (ultima risorsa:
'      in questo caso una finestra di terminale resta visibile)
' Se nessuno dei tre e' disponibile, o se manca main.py, mostra un messaggio
' che spiega ESATTAMENTE cosa manca e cosa fare (es. eseguire prima setup.py),
' invece del generico "ambiente virtuale o file principale non trovato" che
' non distingueva i due casi.
'
' Autore: Samuele Gallo
' ==============================================================================

Option Explicit

Dim objShell, objFSO, strScriptDir, strPythonPath, strMainPath
Dim strIconPath, strDesktopPath, strShortcutPath, objShortcut
Dim strFoundPython

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

' Determinazione dinamica della directory radice del progetto
strScriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

' --- Crea, se non esiste ancora, un collegamento con icona sul Desktop ---
strIconPath = strScriptDir & "\assets\app_icon.ico"
strDesktopPath = objShell.SpecialFolders("Desktop")
strShortcutPath = strDesktopPath & "\Analisi Metrologica.lnk"

If Not objFSO.FileExists(strShortcutPath) Then
    Set objShortcut = objShell.CreateShortcut(strShortcutPath)
    objShortcut.TargetPath = WScript.ScriptFullName
    objShortcut.WorkingDirectory = strScriptDir
    If objFSO.FileExists(strIconPath) Then
        objShortcut.IconLocation = strIconPath
    End If
    objShortcut.Description = "Stereo Metrology Analysis"
    objShortcut.Save
End If

' --- Percorsi dell'ambiente virtuale e dell'entry-point ---
strPythonPath = strScriptDir & "\venv\Scripts\pythonw.exe"
strMainPath = strScriptDir & "\main.py"

' Impostazione della directory di lavoro corrente
objShell.CurrentDirectory = strScriptDir

' main.py e' indispensabile in ogni caso: senza, non si puo' proseguire
If Not objFSO.FileExists(strMainPath) Then
    MsgBox "Impossibile avviare l'applicazione:" & vbCrLf & _
           "Il file main.py non e' stato trovato in:" & vbCrLf & strScriptDir & vbCrLf & vbCrLf & _
           "Controlla di aver scaricato/copiato l'intera cartella del progetto, non solo questo file.", _
           16, "Errore di Inizializzazione"
    WScript.Quit 1
End If

' Sceglie il primo interprete Python disponibile, nell'ordine descritto sopra
If objFSO.FileExists(strPythonPath) Then
    strFoundPython = strPythonPath
Else
    strFoundPython = FindInPath("pythonw.exe")
    If strFoundPython = "" Then
        strFoundPython = FindInPath("python.exe")
    End If
End If

If strFoundPython <> "" Then
    objShell.Run """" & strFoundPython & """ """ & strMainPath & """", 0, False
Else
    MsgBox "Impossibile avviare l'applicazione:" & vbCrLf & _
           "Ambiente virtuale non trovato in:" & vbCrLf & strScriptDir & "\venv" & vbCrLf & _
           "e nessun Python di sistema e' raggiungibile." & vbCrLf & vbCrLf & _
           "Se e' la prima volta che avvii l'app su questo computer, esegui prima setup.py " & _
           "(doppio clic sul file, oppure 'python setup.py' da terminale) per creare " & _
           "l'ambiente virtuale e installare le dipendenze necessarie.", _
           16, "Errore di Inizializzazione"
    WScript.Quit 1
End If

Set objFSO = Nothing
Set objShell = Nothing

' ------------------------------------------------------------------------
' Cerca strExeName in ciascuna delle cartelle elencate nel PATH di sistema.
' Ritorna il percorso completo trovato, oppure stringa vuota se assente.
' ------------------------------------------------------------------------
Function FindInPath(strExeName)
    Dim strPathEnv, arrPaths, i, strCandidate

    FindInPath = ""
    strPathEnv = objShell.ExpandEnvironmentStrings("%PATH%")
    If Len(strPathEnv) = 0 Then Exit Function

    arrPaths = Split(strPathEnv, ";")
    For i = 0 To UBound(arrPaths)
        If Len(Trim(arrPaths(i))) > 0 Then
            strCandidate = arrPaths(i) & "\" & strExeName
            If objFSO.FileExists(strCandidate) Then
                FindInPath = strCandidate
                Exit Function
            End If
        End If
    Next
End Function
