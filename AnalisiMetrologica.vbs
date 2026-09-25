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
Dim strLogPath, strInnerCmd, strCmd, Q
Dim strSetupMarker, objMarker, strSetupPyPath

Q = Chr(34) ' un carattere di virgolette, usato per costruire comandi cmd.exe senza errori di escaping

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
strSetupPyPath = strScriptDir & "\setup.py"

' Marcatore scritto SOLO dopo che l'installazione delle dipendenze e' riuscita
' per intero: a differenza di pythonw.exe (che esiste gia' subito dopo la sola
' creazione del venv, prima ancora che i pacchetti siano installati), questo
' file dice con certezza se il setup e' davvero completo o no.
strSetupMarker = strScriptDir & "\venv\.setup_complete"

' main.py e' indispensabile in ogni caso: senza, non si puo' proseguire
If Not objFSO.FileExists(strMainPath) Then
    MsgBox "Impossibile avviare l'applicazione:" & vbCrLf & _
           "Il file main.py non e' stato trovato in:" & vbCrLf & strScriptDir & vbCrLf & vbCrLf & _
           "Controlla di aver scaricato/copiato l'intera cartella del progetto, non solo questo file.", _
           16, "Errore di Inizializzazione"
    WScript.Quit 1
End If

' setup.py serve solo per il bootstrap (ambiente non ancora configurato), ma se
' manca e' meglio dirlo subito con un messaggio chiaro piuttosto che scoprirlo
' indirettamente da un errore di Python dentro setup_log.txt.
If Not objFSO.FileExists(strSetupMarker) And Not objFSO.FileExists(strSetupPyPath) Then
    MsgBox "Impossibile completare la configurazione:" & vbCrLf & _
           "Il file setup.py non e' stato trovato in:" & vbCrLf & strScriptDir & vbCrLf & vbCrLf & _
           "Controlla di aver copiato/scaricato l'INTERA cartella del progetto da GitHub " & _
           "(non solo alcuni file) nella stessa posizione di questo file .vbs.", _
           16, "Errore di Inizializzazione"
    WScript.Quit 1
End If

' --- Se il setup non risulta completato con successo, esegue il bootstrap ---
If Not objFSO.FileExists(strSetupMarker) Then

    strSystemPython = FindInPath("python.exe")
    If strSystemPython = "" Then
        MsgBox "Prima di poter avviare l'applicazione serve installare Python." & vbCrLf & vbCrLf & _
               "Scarica e installa Python (versione 3.10 o successiva) da:" & vbCrLf & _
               "https://www.python.org/downloads/" & vbCrLf & vbCrLf & _
               "Durante l'installazione spunta l'opzione ""Add python.exe to PATH""," & vbCrLf & _
               "poi riesegui questo file per completare la configurazione automatica." & vbCrLf & vbCrLf & _
               "Nota: se sul PC risultava gia' un ""python.exe"" ma vedi questo messaggio " & _
               "comunque, probabilmente era solo l'alias del Microsoft Store (non un Python " & _
               "vero) — installane uno da python.org come sopra.", _
               48, "Python non trovato"
        WScript.Quit 1
    End If

    MsgBox "Configurazione dell'ambiente in corso (potrebbe richiedere alcuni minuti, " & _
           "in base alla velocita' della connessione)." & vbCrLf & vbCrLf & _
           "Premi OK per continuare: si aprira' una finestra con l'avanzamento della " & _
           "creazione dell'ambiente virtuale; il passo successivo (installazione delle " & _
           "dipendenze) invece procede in background e il suo esito completo viene " & _
           "salvato nel file setup_log.txt, nella cartella del progetto.", _
           64, "Configurazione iniziale"

    ' Crea l'ambiente virtuale (finestra visibile, in attesa del completamento).
    ' Se il venv esiste gia' da un tentativo precedente, ricrearlo non fa danni.
    intExitCode = objShell.Run("""" & strSystemPython & """ -m venv """ & strScriptDir & "\venv""", 1, True)
    If intExitCode <> 0 Or Not objFSO.FileExists(strVenvPython) Then
        MsgBox "Creazione dell'ambiente virtuale non riuscita (codice " & intExitCode & ")." & vbCrLf & _
               "Prova a eseguire manualmente da terminale, nella cartella del progetto:" & vbCrLf & _
               "python -m venv venv", _
               16, "Errore di Configurazione"
        WScript.Quit 1
    End If

    ' Installa le dipendenze e PyTorch tramite setup.py. L'output completo (compresi
    ' gli eventuali errori di pip, es. problemi di connessione) viene salvato per
    ' intero in setup_log.txt: una finestra visibile qui si chiuderebbe troppo in
    ' fretta per riuscire a leggerla, il file invece resta consultabile con calma.
    strLogPath = strScriptDir & "\setup_log.txt"
    strInnerCmd = Q & strVenvPython & Q & " " & Q & strSetupPyPath & Q & _
                  " > " & Q & strLogPath & Q & " 2>&1"
    strCmd = "cmd /c " & Q & strInnerCmd & Q
    intExitCode = objShell.Run(strCmd, 0, True)

    If intExitCode <> 0 Or Not objFSO.FileExists(strVenvPythonw) Then
        MsgBox "L'installazione delle dipendenze non e' andata a buon fine (codice " & intExitCode & ")." & vbCrLf & vbCrLf & _
               "Per vedere il motivo esatto (es. un problema di connessione durante il download), " & _
               "apri con un editor di testo il file:" & vbCrLf & strLogPath & vbCrLf & vbCrLf & _
               "Dopo aver risolto il problema, riesegui questo file per riprovare.", _
               16, "Errore di Configurazione"
        WScript.Quit 1
    End If

    ' Scrive il marcatore SOLO ora che l'installazione e' davvero riuscita, cosi'
    ' i prossimi avvii sapranno con certezza di poter saltare il bootstrap.
    Set objMarker = objFSO.CreateTextFile(strSetupMarker, True)
    objMarker.WriteLine "Setup completato con successo."
    objMarker.Close

    MsgBox "Configurazione completata. L'applicazione si avvia ora.", 64, "Pronto"
End If

' --- Avvio dell'applicativo, senza finestra di console ---
objShell.Run """" & strVenvPythonw & """ """ & strMainPath & """", 0, False

Set objFSO = Nothing
Set objShell = Nothing

' ------------------------------------------------------------------------
' Cerca strExeName in ciascuna delle cartelle elencate nel PATH di sistema.
' Ritorna il percorso completo trovato, oppure stringa vuota se assente.
'
' Salta deliberatamente le cartelle "WindowsApps": Windows 10/11 ci mette
' di default un python.exe "fittizio" (l'alias che rimanda al Microsoft
' Store) che esiste come file ma non funziona come vero interprete se
' lanciato con argomenti come "-m venv" — e' la causa piu' comune del
' codice di errore 9009 durante la creazione dell'ambiente virtuale.
' ------------------------------------------------------------------------
Function FindInPath(strExeName)
    Dim strPathEnv, arrPaths, i, strCandidate

    FindInPath = ""
    strPathEnv = objShell.ExpandEnvironmentStrings("%PATH%")
    If Len(strPathEnv) = 0 Then Exit Function

    arrPaths = Split(strPathEnv, ";")
    For i = 0 To UBound(arrPaths)
        If Len(Trim(arrPaths(i))) > 0 Then
            If InStr(1, arrPaths(i), "WindowsApps", vbTextCompare) = 0 Then
                strCandidate = arrPaths(i) & "\" & strExeName
                If objFSO.FileExists(strCandidate) Then
                    FindInPath = strCandidate
                    Exit Function
                End If
            End If
        End If
    Next
End Function
