"""
Modulo per la gestione dinamica delle dipendenze dell'ambiente di esecuzione.
Fornisce funzioni per la verifica dell'hardware acceleration (NVIDIA CUDA)
e per il ripristino/installazione automatizzata di PyTorch.

Autore: Samuele Gallo
"""

import os
import subprocess
import sys
import shutil
import logging

# Configurazione del logging per tracciabilità accademica/sperimentale
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def check_nvidia_smi() -> bool:
    """
    Interroga il sistema operativo per verificare la presenza dei driver NVIDIA
    e dell'utilità di gestione nvidia-smi.

    :return: True se una GPU NVIDIA è presente e operativa, False altrimenti.
    """
    nvidia_smi_path = shutil.which("nvidia-smi")
    if not nvidia_smi_path:
        return False
    try:
        result = subprocess.run([nvidia_smi_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Errore durante l'esecuzione di nvidia-smi: {e}")
        return False


def get_cuda_status() -> dict:
    """
    Esegue un'analisi diagnostica approfondita sullo stato di PyTorch e dell'accelerazione hardware.

    :return: Dizionario contenente le metriche di stato (disponibilità, nome dispositivo, conteggio).
    """
    status = {
        "cuda_available": False,
        "device_count": 0,
        "device_name": "N/D",
        "torch_version": "Non installato",
        "has_nvidia_driver": check_nvidia_smi()
    }

    try:
        import torch
        status["torch_version"] = torch.__version__
        status["cuda_available"] = torch.cuda.is_available()
        if status["cuda_available"]:
            status["device_count"] = torch.cuda.device_count()
            status["device_name"] = torch.cuda.get_device_name(0)
    except ImportError:
        pass

    return status


def terminate_python_processes():
    """
    Termina eventuali processi Python secondari per rilasciare i lock sui file DLL
    (es. c10.dll) ed evitare PermissionError durante le operazioni di aggiornamento.
    """
    if sys.platform.startswith("win"):
        try:
            current_pid = subprocess.os.getpid()
            cmd = f'taskkill /F /FI "PID ne {current_pid}" /IM python.exe'
            subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            logging.warning(f"Impossibile terminare i processi concorrenti: {e}")


def restart_application() -> None:
    """
    Riavvia l'intero processo dell'applicativo, sostituendo il processo Python
    corrente con una nuova istanza dello stesso comando di avvio.

    Necessario dopo aver reinstallato PyTorch: i binding CUDA (file .dll/.so
    compilati) vengono caricati in memoria una sola volta all'avvio del
    processo e Windows li tiene "bloccati" per tutta la sua durata — non
    esiste un modo per ricaricarli a caldo nello stesso processo, quindi
    l'unico modo reale per "vedere" la nuova installazione e' un riavvio
    completo. os.execv sostituisce il processo corrente stesso (stesso PID),
    quindi dal punto di vista dell'utente e' un riavvio immediato e pulito,
    non l'apertura di una seconda istanza dell'app.
    """
    python = sys.executable
    os.execv(python, [python] + sys.argv)


def install_pytorch_environment(force_cuda: bool = True) -> bool:
    """
    Esegue la riconfigurazione dinamica del framework PyTorch.
    Rileva le specifiche hardware e scarica la build idonea (CUDA 12.1 o CPU).
    
    :param force_cuda: Se True, forza l'installazione dei binding CUDA qualora la GPU sia presente.
    :return: True se l'installazione si conclude con successo, False altrimenti.
    """
    has_gpu = check_nvidia_smi()
    terminate_python_processes()
    
    base_cmd = [
        sys.executable, "-m", "pip", "install", "--force-reinstall",
        "torch", "torchvision", "torchaudio"
    ]
    
    if has_gpu and force_cuda:
        logging.info("Rilevata unità di elaborazione grafica NVIDIA. Avvio configurazione CUDA 12.1...")
        cmd = base_cmd + ["--index-url", "https://download.pytorch.org/whl/cu121"]
    else:
        logging.info("Nessun acceleratore hardware dedicato rilevato. Configurazione build CPU standard...")
        cmd = base_cmd

    try:
        subprocess.check_call(cmd)
        logging.info("Configurazione del framework completata con successo.")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Errore critico durante la fase di installazione: {e}")
        return False
