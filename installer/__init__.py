"""
Installer dell'applicativo: rileva sistema operativo e hardware e installa SOLO
cio' che serve. Usa soltanto la libreria standard, cosi' puo' girare anche con
il Python di sistema prima che esista l'ambiente virtuale.

Componenti:
  core      - tutto cio' che serve per usare l'app (analisi, webcam, GUI), con
              PyTorch nella build migliore per l'hardware (CUDA se c'e' una GPU
              NVIDIA). Installato una volta sola dagli installer per OS.
  training  - solo gli extra dell'addestramento (requirements-training.txt);
              mai installati in automatico: li richiede l'utente dalla pagina
              di training. Serve anche a riparare/attivare la GPU se mancava.

I controlli sulle dipendenze avvengono SOLO qui, durante l'installazione: gli
avvii successivi dell'app non verificano nulla (vedi .install_state.json).

Autore: Samuele Gallo
"""
