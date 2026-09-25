"""
Demo dal vivo: apre la webcam (integrata o una USB esterna collegata) e
mostra in tempo reale il rilevamento YOLO sulle persone inquadrate. Utile
per far vedere rapidamente il modello in azione senza dover prima
registrare foto o video — riusa la stessa pipeline di rilevamento
(ObjectAnalyzer.detect_in_image + render_overlay) usata dalle pagine
Analisi Foto/Video, cosi' la demo mostra esattamente lo stesso
comportamento dell'applicativo.

Uso:
    python tools/webcam_demo.py
    python tools/webcam_demo.py --model models/yolo11n-seg.pt --camera 1
    python tools/webcam_demo.py --class all      # mostra tutte le classi, non solo "person"
    python tools/webcam_demo.py --list-cameras   # elenca le camere disponibili ed esce

Premi 'q' o ESC nella finestra video per uscire.

Autore: Samuele Gallo
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from core.analysis import ObjectAnalyzer, render_overlay

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
DEFAULT_CLASS = "person"


def list_cameras(max_index: int = 5) -> None:
    """Prova ad aprire le prime `max_index` camere e stampa quali rispondono (utile per trovare l'indice di una USB esterna)."""
    print("Ricerca camere disponibili...")
    found = False
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                print(f"  Camera {idx}: disponibile")
                found = True
            cap.release()
    if not found:
        print("  Nessuna camera trovata nei primi indici. Se ne hai collegata una esterna, "
              "prova un indice più alto con --camera N (es. --camera 1, --camera 2...).")


def pick_default_model() -> Optional[Path]:
    """Sceglie il primo modello .pt trovato in models/, se ce n'è uno."""
    if not MODELS_DIR.is_dir():
        return None
    models = sorted(MODELS_DIR.glob("*.pt"))
    return models[0] if models else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo dal vivo: rilevamento YOLO da webcam.")
    parser.add_argument("--model", type=str, default=None,
                         help="Percorso del modello YOLO (.pt). Default: il primo trovato in models/.")
    parser.add_argument("--camera", type=int, default=0,
                         help="Indice della camera da usare (0 = di solito quella integrata del portatile). Default: 0.")
    parser.add_argument("--class", dest="target_class", type=str, default=DEFAULT_CLASS,
                         help=f"Classe da mostrare (default: '{DEFAULT_CLASS}'). Usa 'all' per mostrare tutte le classi rilevate.")
    parser.add_argument("--list-cameras", action="store_true",
                         help="Elenca le camere disponibili (integrata + eventuali USB esterne) ed esce.")
    args = parser.parse_args()

    if args.list_cameras:
        list_cameras()
        return

    model_path = Path(args.model) if args.model else pick_default_model()
    if model_path is None or not model_path.is_file():
        print("Nessun modello YOLO trovato. Specifica un percorso valido con --model, "
              "oppure metti un file .pt dentro models/.")
        sys.exit(1)

    print(f"Caricamento modello: {model_path}")
    analyzer = ObjectAnalyzer(str(model_path))

    target_label = None if args.target_class.strip().lower() == "all" else args.target_class

    print(f"Apertura camera {args.camera}...")
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"Impossibile aprire la camera {args.camera}. "
              f"Prova 'python tools/webcam_demo.py --list-cameras' per vedere quali sono disponibili "
              f"(se è una USB esterna, potrebbe non essere all'indice 0).")
        sys.exit(1)

    # Chiede alla camera una risoluzione piu' alta (se la supporta): se non e'
    # disponibile, la camera restituira' comunque la risoluzione massima che
    # ha, senza errori — richiederla non fa mai danno.
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    window_name = "Demo YOLO — premi 'q' per uscire"

    # WINDOW_NORMAL rende la finestra ridimensionabile trascinando i bordi
    # (per default OpenCV la blocca alla dimensione esatta dell'immagine) —
    # resizeWindow le da' anche una dimensione iniziale piu' grande.
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

    print("Demo avviata. Premi 'q' o ESC nella finestra video per uscire.")

    prev_time = time.time()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Impossibile leggere un fotogramma dalla camera.")
                break

            detections = analyzer.detect_in_image(frame, timestamp="live")
            if target_label is not None:
                target_lower = target_label.strip().lower()
                detections = [d for d in detections if d.label.strip().lower() == target_lower]

            overlay = render_overlay(frame, detections)

            now = time.time()
            fps = 1.0 / max(now - prev_time, 1e-6)
            prev_time = now
            cv2.putText(overlay, f"FPS: {fps:.1f}  |  Rilevati: {len(detections)}", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow(window_name, overlay)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):  # 'q' oppure ESC
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
