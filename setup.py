"""
Script autonomo di configurazione dell'ambiente virtuale per la tesi di laurea.
Gestisce l'installazione sequenziale delle dipendenze generali e del framework PyTorch.

Autore: Samuele Gallo
"""

import subprocess
import sys
import os
from core.environment_manager import install_pytorch_environment, get_cuda_status

def setup_workspace():
    print("======================================================================")
    print("        CONFIGURAZIONE AUTOMATIZZATA DELL'AMBIENTE DI CALCOLO         ")
    print("======================================================================")
    
    # 1. Installazione dei requisiti generali
    req_file = "requirements.txt"
    if os.path.exists(req_file):
        print(f"\n[1/2] Installazione delle librerie da {req_file}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file])
            print("[OK] Dipendenze generali installate correttamente.")
        except subprocess.CalledProcessError:
            print("[ERRORE] Errore nell'installazione dei requisiti standard.")
            sys.exit(1)
    else:
        print(f"[ATTENZIONE] File {req_file} non trovato. Procedimento limitato a PyTorch.")

    # 2. Riconfigurazione dinamica PyTorch per l'hardware rilevato
    print("\n[2/2] Rilevamento e configurazione del supporto hardware (CUDA/CPU)...")
    success = install_pytorch_environment()
    
    if success:
        status = get_cuda_status()
        print("\n----------------------------------------------------------------------")
        print("ESITO VERIFICA CONFIGURAZIONE:")
        print(f" - Versione PyTorch: {status['torch_version']}")
        print(f" - Accelerazione CUDA: {'Abilitata' if status['cuda_available'] else 'Disabilitata'}")
        print(f" - Dispositivo grafico: {status['device_name']}")
        print("----------------------------------------------------------------------")
        print("[OK] Ambiente configurato e pronto all'esecuzione delle sessioni sperimentali.")
    else:
        print("[ERRORE] Configurazione dell'accelerazione hardware non riuscita.")

if __name__ == "__main__":
    setup_workspace()