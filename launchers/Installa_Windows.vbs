' ==============================================================================
' Installer per WINDOWS - Analisi Metrologica
' ==============================================================================
' Da eseguire una sola volta (doppio clic). Installa SOLO cio' che serve a questo
' computer:
'   1. Python (se manca un Python >= 3.10): build ufficiale da python.org,
'      installazione per l'utente corrente, senza diritti di amministratore;
'   2. l'ambiente virtuale "venv" e i componenti base dell'app (PyTorch nella
'      build migliore per l'hardware: CUDA se c'e' una GPU NVIDIA, altrimenti CPU
'      leggera; + librerie), scelti dal pacchetto installer/.
' Solo gli extra del TRAINING si installano dopo, dalla pagina di training dell'app.
' Il risultato viene registrato in .install_state.json: gli avvii successivi non
' controllano piu' nulla. Per reinstallare/riparare basta rieseguire questo file
' (aggiungi "/force" come argomento per forzare la reinstallazione).
'
' Autore: Samuele Gallo
' ==============================================================================

Option Explicit

Dim objShell, objFSO, strScriptDir, strVenvPython, strSystemPython
Dim intExitCode, blnNeedPythonInstall, strPyVersion, strPyInstallerUrl, strForce, Q

Const MIN_PY_MAJOR = 3
Const MIN_PY_MINOR = 10
Const MIN_PY_NUM = 310

Q = Chr(34)

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strScriptDir = objFSO.GetParentFolderName(objFSO.GetParentFolderName(WScript.ScriptFullName)) ' radice del progetto (questo file sta in launchers\)
objShell.CurrentDirectory = strScriptDir

strPyVersion = "3.12.6"
strPyInstallerUrl = "https://www.python.org/ftp/python/" & strPyVersion & "/python-" & strPyVersion & "-amd64.exe"
strVenvPython = strScriptDir & "\venv\Scripts\python.exe"

strForce = ""
If WScript.Arguments.Count > 0 Then
    If LCase(WScript.Arguments(0)) = "/force" Then strForce = " --force"
End If

If Not objFSO.FileExists(strScriptDir & "\main.py") Or Not objFSO.FolderExists(strScriptDir & "\installer") Then
    MsgBox "File del progetto mancanti (main.py o cartella installer) in:" & vbCrLf & strScriptDir & vbCrLf & vbCrLf & _
           "Scarica l'INTERA cartella del progetto, non solo questo file.", 16, "Errore di Inizializzazione"
    WScript.Quit 1
End If

strSystemPython = FindInPath("python.exe")
blnNeedPythonInstall = False
If strSystemPython = "" Then
    blnNeedPythonInstall = True
ElseIf GetPythonVersionNum(strSystemPython) < MIN_PY_NUM Then
    blnNeedPythonInstall = True
End If

If blnNeedPythonInstall Then
    ' Un Python gia' installato per l'utente (ma non nel PATH) va benissimo
    strSystemPython = FindInstalledPython()
    If strSystemPython <> "" Then
        If GetPythonVersionNum(strSystemPython) < MIN_PY_NUM Then strSystemPython = ""
    End If
End If

If strSystemPython = "" Then
    MsgBox "Non e' stato trovato un Python idoneo (serve la versione " & MIN_PY_MAJOR & "." & MIN_PY_MINOR & _
           " o successiva)." & vbCrLf & vbCrLf & _
           "Verra' scaricato e installato automaticamente Python " & strPyVersion & _
           " (solo per l'utente corrente, NON servono diritti di amministratore)." & vbCrLf & vbCrLf & _
           "Premi OK per continuare.", 64, "Installazione automatica di Python"

    strSystemPython = InstallPythonAutomatically()

    If strSystemPython = "" Then
        MsgBox "L'installazione automatica di Python non e' riuscita " & _
               "(connessione assente o download bloccato da antivirus/firewall)." & vbCrLf & vbCrLf & _
               "Installalo a mano da https://www.python.org/downloads/ (spunta ""Add python.exe to PATH"") " & _
               "e riesegui questo file.", 16, "Installazione non riuscita"
        WScript.Quit 1
    End If
End If

' --- Percorso preferito: finestra grafica con barra di avanzamento (nessun terminale) ---
Dim strGuiPy, strGuiScript
strGuiPy = objFSO.GetParentFolderName(strSystemPython) & "\pythonw.exe"
strGuiScript = strScriptDir & "\distribution\installer_gui.py"
If objFSO.FileExists(strGuiPy) And objFSO.FileExists(strGuiScript) Then
    If objShell.Run(Q & strSystemPython & Q & " -c ""import tkinter""", 0, True) = 0 Then
        objShell.Run Q & strGuiPy & Q & " " & Q & strGuiScript & Q & " --dest " & Q & strScriptDir & Q, 1, True
        WScript.Quit 0
    End If
End If

' --- Ripiego (tkinter assente): installazione in background, senza finestra di terminale ---
MsgBox "Verranno installati solo i componenti necessari a questo computer." & vbCrLf & vbCrLf & _
       "L'installazione procede in background (qualche minuto, in base alla connessione): " & _
       "attendi il messaggio di conclusione.", 64, "Installazione dell'ambiente"

' L'installer (pacchetto installer/) usa il Python di sistema solo per creare il venv,
' poi prosegue da solo dentro il venv. Nessuna finestra, si attende la fine.
intExitCode = objShell.Run("cmd /c " & Q & Q & strSystemPython & Q & " -m installer --os windows --component core --yes" & strForce & Q, 0, True)

If intExitCode <> 0 Or Not objFSO.FileExists(strScriptDir & "\.install_state.json") Then
    MsgBox "L'installazione non e' andata a buon fine (codice " & intExitCode & ")." & vbCrLf & vbCrLf & _
           "Dettagli nel file:" & vbCrLf & strScriptDir & "\install_log.txt" & vbCrLf & vbCrLf & _
           "Risolto il problema (es. connessione), riesegui questo file.", 16, "Errore di Installazione"
    WScript.Quit 1
End If

MsgBox "Installazione completata." & vbCrLf & "Avvia l'app con ""AnalisiMetrologica.vbs"" o con il collegamento sul Desktop.", _
       64, "Pronto"

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
