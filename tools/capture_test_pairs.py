"""
Modulo Utility per la Cattura di Coppie di Test Stereo
======================================================
Consente la registrazione guidata e temporizzata di fotogrammi stereo
da due moduli cam (Destra / Sinistra) per il collaudo della pipeline metrologica.

Ogni esecuzione crea una nuova cartella "testN" (incrementale) dentro
datasets/, cosi' le acquisizioni compaiono automaticamente nel menu a
tendina "Cartella dataset" dell'app senza doverle aggiungere manualmente.

Il formato di output replica ESATTAMENTE quello del demone Sensing-Rigs
(vedi constants.c: DAEMON_PATH_CAP="captures/", DAEMON_PATH_RX="rx/",
DAEMON_PATH_LX="lx/", nome file = timestamp Unix epoch, es. "1723130400.jpg"):

    datasets/testN/
    ├── rx/
    │   ├── 1723130400.jpg
    │   └── 1723130403.jpg
    └── lx/
        ├── 1723130400.jpg
        └── 1723130403.jpg

Autore: Candidato Tesi
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import cv2

# --- CONFIGURAZIONE DISPOSITIVI E PARAMETRI DI ACQUISIZIONE ---
# Nota: questi indici si riferiscono alle webcam collegate alla macchina di
# sviluppo (non corrispondono necessariamente agli indici camera 0/1 usati
# dal demone sul Raspberry, che sono un dettaglio hardware del Pi).
CAM_RIGHT_INDEX: int = 0
CAM_LEFT_INDEX: int = 1

FRAME_WIDTH: int = 1280
FRAME_HEIGHT: int = 720

TOTAL_CAPTURES: int = 20
INTERVAL_SECONDS: float = 3.0

# Cartella che raccoglie tutti i dataset (stessa usata dalla GUI dell'app)
DATASETS_DIR = Path(__file__).parent.parent / "datasets"

_TEST_DIR_PATTERN = re.compile(r"^test(\d+)$")


def _get_next_test_dir(base_dir: Path) -> Path:
    """Determina il prossimo nome 'testN' libero e crea la cartella corrispondente."""
    base_dir.mkdir(parents=True, exist_ok=True)

    max_n = 0
    for entry in base_dir.iterdir():
        if entry.is_dir():
            match = _TEST_DIR_PATTERN.match(entry.name)
            if match:
                max_n = max(max_n, int(match.group(1)))

    new_dir = base_dir / f"test{max_n + 1}"
    new_dir.mkdir(parents=True, exist_ok=False)
    return new_dir


def run_test_capture() -> None:
    """Esegue il ciclo di acquisizione automatica delle coppie di immagini stereo."""
    output_dir = _get_next_test_dir(DATASETS_DIR)
    rx_dir = output_dir / "rx"
    lx_dir = output_dir / "lx"
    rx_dir.mkdir(parents=True, exist_ok=True)
    lx_dir.mkdir(parents=True, exist_ok=True)

    cap_right = cv2.VideoCapture(CAM_RIGHT_INDEX)
    cap_left = cv2.VideoCapture(CAM_LEFT_INDEX)

    for cap in (cap_right, cap_left):
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    captures_count: int = 0
    last_capture_time: float | None = None
    is_active: bool = False
    status_message: str = "Premi SPAZIO per iniziare  |  Q per uscire"

    print(f"[INFO] Le coppie verranno salvate in: {output_dir}  (formato rx/lx, come il demone reale)")
    print("[INFO] Finestre di acquisizione aperte. Premi SPAZIO per avviare il timer.")

    try:
        while captures_count < TOTAL_CAPTURES:
            ret_r, img_right = cap_right.read()
            ret_l, img_left = cap_left.read()

            if not ret_r or not ret_l:
                print("[ERROR] Impossibile acquisire il flusso da una o entrambe le telecamere.")
                break

            now = time.time()

            # Scatto automatico temporizzato
            if is_active and (last_capture_time is None or (now - last_capture_time) >= INTERVAL_SECONDS):
                # Timestamp Unix epoch (intero), come genera rpicam-still con --timestamp
                epoch_ts = int(now)

                path_r = rx_dir / f"{epoch_ts}.jpg"
                path_l = lx_dir / f"{epoch_ts}.jpg"

                cv2.imwrite(str(path_r), img_right)
                cv2.imwrite(str(path_l), img_left)

                captures_count += 1
                last_capture_time = now
                status_message = "Riposizionare il target..."
                print(f"[{captures_count}/{TOTAL_CAPTURES}] Acquisita coppia: {epoch_ts}")

            display_r = img_right.copy()
            display_l = img_left.copy()

            # Calcolo del conto alla rovescia
            if is_active and last_capture_time is not None:
                time_remaining = INTERVAL_SECONDS - (now - last_capture_time)
                if time_remaining > 0:
                    status_message = f"Prossimo scatto tra {time_remaining:.1f}s  |  Muovere il target"

            # Rendering barra informativa (Camera Destra)
            cv2.rectangle(display_r, (0, 0), (FRAME_WIDTH, 50), (0, 0, 0), -1)
            cv2.putText(
                display_r,
                f"Scatti: {captures_count}/{TOTAL_CAPTURES}  |  {status_message}",
                (10, 33),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            )

            # Rendering barra informativa (Camera Sinistra)
            cv2.rectangle(display_l, (0, 0), (FRAME_WIDTH, 50), (0, 0, 0), -1)
            cv2.putText(
                display_l,
                "CAMERA SINISTRA (L)",
                (10, 33),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 200, 255),
                2,
            )

            # Feedback visivo all'avvenuto scatto (flash verde)
            if last_capture_time is not None and (now - last_capture_time) < 0.4:
                cv2.rectangle(display_r, (0, 0), (FRAME_WIDTH, FRAME_HEIGHT), (0, 255, 0), 8)
                cv2.rectangle(display_l, (0, 0), (FRAME_WIDTH, FRAME_HEIGHT), (0, 255, 0), 8)
                cv2.putText(
                    display_r,
                    "ACQUISITO",
                    (450, 390),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.8,
                    (0, 255, 0),
                    4,
                )

            cv2.imshow("Acquisizione Stereo - Camera Destra (R)", display_r)
            cv2.imshow("Acquisizione Stereo - Camera Sinistra (L)", display_l)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == ord("Q"):
                break
            if key == ord(" ") and not is_active:
                is_active = True
                last_capture_time = None
                status_message = "Acquisizione avviata"
                print("[INFO] Sequenza di acquisizione temporizzata avviata.")

    finally:
        cap_right.release()
        cap_left.release()
        cv2.destroyAllWindows()
        print(f"\n[INFO] Procedura terminata. {captures_count} coppie salvate in: {output_dir}")


if __name__ == "__main__":
    run_test_capture()