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
' Se sul computer non e' presente un Python di versione sufficiente (minimo
' 3.10), questo script lo scarica e lo installa da solo (build ufficiale da
' python.org, installazione "per l'utente corrente": NON richiede diritti di
' amministratore) prima di proseguire con la creazione dell'ambiente virtuale
' — serve solo una connessione a Internet, nessun passaggio manuale.
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
Dim blnNeedPythonInstall, strPyVersion, strPyInstallerUrl

Const MIN_PY_MAJOR = 3
Const MIN_PY_MINOR = 10
Const MIN_PY_NUM = 310 ' MIN_PY_MAJOR * 100 + MIN_PY_MINOR, VBScript non valuta costanti tra loro

Q = Chr(34) ' un carattere di virgolette, usato per costruire comandi cmd.exe/powershell senza errori di escaping

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strScriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
objShell.CurrentDirectory = strScriptDir

' Versione di Python installata automaticamente quando serve (build ufficiale
' a 64 bit da python.org). Aggiornare qui se in futuro si vuole puntare a una
' versione piu' recente.
strPyVersion = "3.12.6"
strPyInstallerUrl = "https://www.python.org/ftp/python/" & strPyVersion & "/python-" & strPyVersion & "-amd64.exe"

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
    blnNeedPythonInstall = False

    If strSystemPython = "" Then
        blnNeedPythonInstall = True
    ElseIf GetPythonVersionNum(strSystemPython) < MIN_PY_NUM Then
        blnNeedPythonInstall = True
    End If

    If blnNeedPythonInstall Then
        MsgBox "Non e' stato trovato un Python idoneo sul computer (serve la versione " & _
               MIN_PY_MAJOR & "." & MIN_PY_MINOR & " o successiva)." & vbCrLf & vbCrLf & _
               "Verra' scaricata e installata automaticamente la versione " & strPyVersion & _
               " (solo per l'utente corrente: NON servono diritti di amministratore)." & vbCrLf & vbCrLf & _
               "Premi OK per continuare: il download e l'installazione richiedono qualche minuto, " & _
               "in base alla velocita' della connessione.", _
               64, "Installazione automatica di Python"

        strSystemPython = InstallPythonAutomatically()

        If strSystemPython = "" Then
            MsgBox "L'installazione automatica di Python non e' riuscita " & _
                   "(probabile problema di connessione, oppure un blocco del download da parte " & _
                   "dell'antivirus/firewall)." & vbCrLf & vbCrLf & _
                   "Puoi installarlo manualmente da:" & vbCrLf & "https://www.python.org/downloads/" & vbCrLf & vbCrLf & _
                   "Durante l'installazione spunta l'opzione ""Add python.exe to PATH""," & vbCrLf & _
                   "poi riesegui questo file per completare la configurazione automatica.", _
                   16, "Installazione automatica non riuscita"
            WScript.Quit 1
        End If
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

' ------------------------------------------------------------------------
' Esegue "<strPyExe> --version" e ne legge l'output (es. "Python 3.11.4")
' per ricavare un numero comparabile major*100+minor (es. 311). Ritorna 0
' se non riesce a determinare la versione (equivale a "non idoneo": fa si'
' che venga proposta l'installazione automatica anziche' un crash piu' avanti).
' ------------------------------------------------------------------------
Function GetPythonVersionNum(strPyExe)
    Dim objExec, strOut, re, mt

    GetPythonVersionNum = 0

    On Error Resume Next
    Set objExec = objShell.Exec(Q & strPyExe & Q & " --version")
    If Err.Number <> 0 Then
        Err.Clear
        On Error Goto 0
        Exit Function
    End If
    On Error Goto 0

    Do While objExec.Status = 0
        WScript.Sleep 50
    Loop

    strOut = ""
    On Error Resume Next
    strOut = objExec.StdOut.ReadAll() & objExec.StdErr.ReadAll() ' alcune versioni di Python stampano su stderr
    On Error Goto 0

    Set re = New RegExp
    re.Pattern = "Python\s+(\d+)\.(\d+)"
    re.IgnoreCase = True

    If re.Test(strOut) Then
        Set mt = re.Execute(strOut)
        GetPythonVersionNum = CInt(mt(0).SubMatches(0)) * 100 + CInt(mt(0).SubMatches(1))
    End If
End Function

' ------------------------------------------------------------------------
' Scarica ed installa automaticamente Python (build ufficiale da python.org,
' installazione "per l'utente corrente": non richiede diritti di
' amministratore) tramite un piccolo script PowerShell generato al volo.
' Ritorna il percorso completo del python.exe appena installato, oppure
' stringa vuota se qualcosa e' andato storto (nessuna connessione, download
' bloccato, installazione fallita...).
' ------------------------------------------------------------------------
Function InstallPythonAutomatically()
    Dim strPs1Path, strInstallerPath, objPs1, strPsCmd, strFound

    InstallPythonAutomatically = ""

    strPs1Path = strScriptDir & "\_install_python.ps1"
    strInstallerPath = strScriptDir & "\_python_installer.exe"

    ' Script PowerShell generato al volo: scarica l'installer ufficiale e lo
    ' esegue in modalita' silenziosa, senza interazione dell'utente.
    On Error Resume Next
    Set objPs1 = objFSO.CreateTextFile(strPs1Path, True)
    objPs1.WriteLine "param([string]$Url, [string]$Dest)"
    objPs1.WriteLine "$ErrorActionPreference = 'Stop'"
    objPs1.WriteLine "try {"
    objPs1.WriteLine "    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12"
    objPs1.WriteLine "    Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing"
    objPs1.WriteLine "    Start-Process -FilePath $Dest -ArgumentList @(" & _
                      "'/quiet','InstallAllUsers=0','PrependPath=1','Include_launcher=0','Include_test=0'" & _
                      ") -Wait"
    objPs1.WriteLine "    exit 0"
    objPs1.WriteLine "} catch {"
    objPs1.WriteLine "    Write-Output $_.Exception.Message"
    objPs1.WriteLine "    exit 1"
    objPs1.WriteLine "}"
    objPs1.Close
    On Error Goto 0

    If Not objFSO.FileExists(strPs1Path) Then Exit Function

    strPsCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & Q & strPs1Path & Q & _
               " -Url " & Q & strPyInstallerUrl & Q & " -Dest " & Q & strInstallerPath & Q

    On Error Resume Next
    objShell.Run strPsCmd, 1, True
    On Error Goto 0

    ' Pulizia dei file temporanei (installer + script), a prescindere dall'esito
    On Error Resume Next
    If objFSO.FileExists(strInstallerPath) Then objFSO.DeleteFile strInstallerPath, True
    If objFSO.FileExists(strPs1Path) Then objFSO.DeleteFile strPs1Path, True
    On Error Goto 0

    strFound = FindInstalledPython()
    If strFound <> "" And GetPythonVersionNum(strFound) >= MIN_PY_NUM Then
        InstallPythonAutomatically = strFound
    End If
End Function

' ------------------------------------------------------------------------
' Cerca un python.exe installato "per l'utente corrente" nella posizione di
' default dell'installer ufficiale (%LocalAppData%\Programs\Python\Python3xx).
' ------------------------------------------------------------------------
Function FindInstalledPython()
    Dim strBase, objFolder, objSub, strCandidate

    FindInstalledPython = ""
    strBase = objShell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python"

    If objFSO.FolderExists(strBase) Then
        Set objFolder = objFSO.GetFolder(strBase)
        For Each objSub In objFolder.SubFolders
            If InStr(1, objSub.Name, "Python", vbTextCompare) = 1 Then
                strCandidate = objSub.Path & "\python.exe"
                If objFSO.FileExists(strCandidate) Then
                    FindInstalledPython = strCandidate
                    Exit Function
                End If
            End If
        Next
    End If
End Function
