' ==============================================================================
' Modulo di Avvio dell'Applicativo (GUI Launcher con Bootstrap Automatico)
' ==============================================================================
' Al primo avvio su un nuovo computer (ambiente virtuale assente), crea da
' solo l'ambiente virtuale e installa tutte le dipendenze (incluso PyTorch,
' tramite setup.py) prima di avviare l'app — basta scaricare la cartella del
' progetto ed eseguire questo file, senza passaggi manuali da terminale.
' Dalle volte successive (ambiente gia' pronto) l'avvio resta rapido e
' silenzioso come prima.
'
' Limite noto: questo script NON installa Python stesso. Se sul computer non
' e' presente nessun interprete Python raggiungibile, mostra un messaggio che
' indica di installarlo da python.org prima di riprovare — installare Python
' silenziosamente da uno script .vbs non e' un'operazione affidabile da fare
' "alla cieca" (varia troppo tra versioni di Windows, richiede spesso diritti
' di amministratore, e va testata su macchine reali prima di potersene fidare).
'
' Al primo avvio crea inoltre un collegamento con l'icona dell'applicativo sul
' Desktop ("Analisi Metrologica.lnk"): un file .vbs non puo' avere un'icona
' propria in Windows, solo un collegamento .lnk puo' averla.
'
' Autore: Samuele Gallo
' ==============================================================================

Option Explicit

Dim objShell, objFSO, strScriptDir, strVenvPythonw, strVenvPython, strMainPath
Dim strIconPath, strDesktopPath, strShortcutPath, objShortcut
Dim strSystemPython, intExitCode

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strScriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
objShell.CurrentDirectory = strScriptDir

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
strVenvPythonw = strScriptDir & "\venv\Scripts\pythonw.exe"
strVenvPython = strScriptDir & "\venv\Scripts\python.exe"
strMainPath = strScriptDir & "\main.py"

' main.py e' indispensabile in ogni caso: senza, non si puo' proseguire
If Not objFSO.FileExists(strMainPath) Then
    MsgBox "Impossibile avviare l'applicazione:" & vbCrLf & _
           "Il file main.py non e' stato trovato in:" & vbCrLf & strScriptDir & vbCrLf & vbCrLf & _
           "Controlla di aver scaricato/copiato l'intera cartella del progetto, non solo questo file.", _
           16, "Errore di Inizializzazione"
    WScript.Quit 1
End If

' --- Se l'ambiente virtuale non esiste ancora, esegue il bootstrap ---
If Not objFSO.FileExists(strVenvPythonw) Then

    strSystemPython = FindInPath("python.exe")
    If strSystemPython = "" Then
        MsgBox "Prima di poter avviare l'applicazione serve installare Python." & vbCrLf & vbCrLf & _
               "Scarica e installa Python (versione 3.10 o successiva) da:" & vbCrLf & _
               "https://www.python.org/downloads/" & vbCrLf & vbCrLf & _
               "Durante l'installazione spunta l'opzione ""Add python.exe to PATH""," & vbCrLf & _
               "poi riesegui questo file per completare la configurazione automatica.", _
               48, "Python non trovato"
        WScript.Quit 1
    End If

    MsgBox "Prima esecuzione su questo computer: l'applicazione configurera' " & _
           "automaticamente l'ambiente necessario (potrebbe richiedere alcuni minuti, " & _
           "in base alla velocita' della connessione)." & vbCrLf & vbCrLf & _
           "Premi OK per continuare: si aprira' una finestra con l'avanzamento " & _
           "dell'installazione, che si chiudera' da sola al termine.", _
           64, "Configurazione iniziale"

    ' Crea l'ambiente virtuale (finestra visibile, in attesa del completamento)
    intExitCode = objShell.Run("""" & strSystemPython & """ -m venv """ & strScriptDir & "\venv""", 1, True)
    If intExitCode <> 0 Or Not objFSO.FileExists(strVenvPython) Then
        MsgBox "Creazione dell'ambiente virtuale non riuscita (codice " & intExitCode & ")." & vbCrLf & _
               "Prova a eseguire manualmente da terminale, nella cartella del progetto:" & vbCrLf & _
               "python -m venv venv", _
               16, "Errore di Configurazione"
        WScript.Quit 1
    End If

    ' Installa le dipendenze e PyTorch tramite setup.py (finestra visibile, in attesa)
    intExitCode = objShell.Run("""" & strVenvPython & """ """ & strScriptDir & "\setup.py""", 1, True)
    If intExitCode <> 0 Or Not objFSO.FileExists(strVenvPythonw) Then
        MsgBox "L'installazione delle dipendenze non e' andata a buon fine (codice " & intExitCode & ")." & vbCrLf & _
               "Controlla la connessione a Internet e riprova eseguendo di nuovo questo file." & vbCrLf & _
               "In alternativa, esegui manualmente da terminale, nella cartella del progetto:" & vbCrLf & _
               "venv\Scripts\python.exe setup.py", _
               16, "Errore di Configurazione"
        WScript.Quit 1
    End If

    MsgBox "Configurazione completata. L'applicazione si avvia ora.", 64, "Pronto"
End If

' --- Avvio dell'applicativo, senza finestra di console ---
objShell.Run """" & strVenvPythonw & """ """ & strMainPath & """", 0, False

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
