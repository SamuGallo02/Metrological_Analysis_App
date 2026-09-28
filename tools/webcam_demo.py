"""
Demo dal vivo: apre la webcam (integrata o una USB esterna collegata) e
mostra in tempo reale il rilevamento YOLO sui soggetti inquadrati. Utile
per far vedere rapidamente il modello in azione senza dover prima
registrare foto o video — riusa la stessa pipeline di rilevamento
(ObjectAnalyzer.detect_in_image + render_overlay) usata dalle pagine
Analisi Foto/Video, cosi' la demo mostra esattamente lo stesso
comportamento dell'applicativo.

Supporta anche una modalita' STEREO DAL VIVO, per chi ha collegato il
sensing-rig con due camere sincronizzate: in questo caso riusa
ObjectAnalyzer.analyze_frame_pair (la stessa pipeline dell'Analisi Video
Stereo) per mostrare, oltre al rilevamento, anche dimensioni e distanza
reali stimate frame per frame — con la calibrazione stereo salvata
dall'app (stereo_calibration.json), se presente.

Uso:
    python tools/webcam_demo.py
    python tools/webcam_demo.py --model models/yolo11n-seg.pt --camera 1
    python tools/webcam_demo.py --class all      # mostra tutte le classi, non solo "person"
    python tools/webcam_demo.py --list-cameras   # elenca le camere disponibili ed esce
    python tools/webcam_demo.py --mode stereo --camera-left 1 --camera-right 2

Premi 'q' o ESC in una finestra video per uscire.

Autore: Samuele Gallo
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

from core.analysis import ObjectAnalyzer, ObjectDetection, render_overlay
from core.calibration import load_calibration
from core.camera_utils import list_available_cameras, open_camera

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
DEFAULT_CLASS = "person"


def list_cameras(max_index: int = 6) -> List[int]:
    """Elenca le camere disponibili (integrata + eventuali USB esterne) e le stampa a schermo."""
    print("Ricerca camere disponibili...")
    found = list_available_cameras(max_index)
    if found:
        for idx in found:
            print(f"  Camera {idx}: disponibile")
        if len(found) >= 2:
            print(f"\n  Rilevate {len(found)} camere: puoi usare la modalita' stereo dal vivo, es.:")
            print(f"    python tools/webcam_demo.py --mode stereo --camera-left {found[0]} --camera-right {found[1]}")
    else:
        print("  Nessuna camera trovata nei primi indici. Se ne hai collegata una esterna, "
              "prova un indice più alto con --camera N (es. --camera 1, --camera 2...).")
    return found


def pick_default_model() -> Optional[Path]:
    """Sceglie il primo modello .pt trovato in models/, se ce n'è uno."""
    if not MODELS_DIR.is_dir():
        return None
    models = sorted(MODELS_DIR.glob("*.pt"))
    return models[0] if models else None


def _draw_stereo_overlay(image, detections: List[ObjectDetection]):
    """
    Come core.analysis.render_overlay, ma la didascalia include anche
    dimensioni e distanza reali quando disponibili (il punto della modalita'
    stereo). Tenuta qui, separata da render_overlay, per non appesantire con
    del testo specifico-demo la funzione di overlay usata da tutta l'app.
    """
    overlay = image.copy()

    for det in detections:
        cv2.drawContours(overlay, [det.contour], -1, (0, 255, 0), 2)
        cv2.ellipse(overlay, det.ellipse, (0, 165, 255), 2)

        id_str = f"[{det.track_id}] " if det.track_id else ""
        parts = [f"{id_str}{det.label}"]
        if det.length_mm is not None and det.width_mm is not None:
            parts.append(f"{det.length_mm:.0f}x{det.width_mm:.0f}mm")
        if det.contact_distance_mm is not None:
            parts.append(f"dist {det.contact_distance_mm:.0f}mm")
        caption = "  ".join(parts)

        txt_size, _ = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        tx, ty = det.bbox_xyxy[0], max(det.bbox_xyxy[1] - 8, 20)
        cv2.rectangle(overlay, (tx, ty - txt_size[1] - 4), (tx + txt_size[0] + 4, ty + 4), (0, 0, 0), -1)
        cv2.putText(overlay, caption, (tx + 2, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)

    return overlay


def _resolve_model(args) -> Path:
    model_path = Path(args.model) if args.model else pick_default_model()
    if model_path is None or not model_path.is_file():
        print("Nessun modello YOLO trovato. Specifica un percorso valido con --model, "
              "oppure metti un file .pt dentro models/.")
        sys.exit(1)
    return model_path


def run_mono(args) -> None:
    """Modalita' originale: una sola camera, solo rilevamento (nessuna misura, come Analisi Foto/Video singola)."""
    model_path = _resolve_model(args)
    print(f"Caricamento modello: {model_path}")
    analyzer = ObjectAnalyzer(str(model_path))

    target_label = None if args.target_class.strip().lower() == "all" else args.target_class

    print(f"Apertura camera {args.camera}...")
    cap = open_camera(args.camera)
    if cap is None:
        print(f"Impossibile aprire la camera {args.camera} (o non restituisce fotogrammi validi). "
              f"Prova 'python tools/webcam_demo.py --list-cameras' per vedere quali sono disponibili "
              f"(se è una USB esterna, potrebbe non essere all'indice 0).")
        sys.exit(1)

    window_name = "Demo YOLO - premi 'q' per uscire"
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
            if key in (ord("q"), 27):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def run_stereo(args) -> None:
    """
    Modalita' stereo dal vivo: due camere sincronizzate (il sensing-rig),
    misure reali frame per frame come nell'Analisi Video Stereo — con la
    differenza che qui le camere sono live invece che due file video.
    """
    if args.camera_left is None or args.camera_right is None:
        available = list_cameras()
        if len(available) < 2:
            print("\nServono almeno due camere per la modalita' stereo dal vivo "
                  f"(ne sono state trovate {len(available)}). Collega il sensing-rig e riprova.")
            sys.exit(1)
        print("\nSpecifica quali usare con --camera-left e --camera-right, es.:")
        print(f"    python tools/webcam_demo.py --mode stereo --camera-left {available[0]} --camera-right {available[1]}")
        sys.exit(1)

    if args.camera_left == args.camera_right:
        print("Camera sinistra e destra non possono coincidere.")
        sys.exit(1)

    model_path = _resolve_model(args)
    stereo_config = load_calibration()
    print(f"Caricamento modello: {model_path}")
    print(f"Calibrazione stereo in uso: baseline={stereo_config.baseline_mm}mm, "
          f"focale={stereo_config.focal_length_px}px")
    analyzer = ObjectAnalyzer(str(model_path), stereo_config=stereo_config)

    target_label = None if args.target_class.strip().lower() == "all" else args.target_class

    print(f"Apertura camera sinistra (indice {args.camera_left})...")
    cap_left = open_camera(args.camera_left)
    print(f"Apertura camera destra (indice {args.camera_right})...")
    cap_right = open_camera(args.camera_right)

    if cap_left is None or cap_right is None:
        print("Impossibile aprire una delle due camere (o non restituisce fotogrammi validi). "
              "Prova 'python tools/webcam_demo.py --list-cameras' per verificare gli indici disponibili.")
        if cap_left is not None:
            cap_left.release()
        if cap_right is not None:
            cap_right.release()
        sys.exit(1)

    window_left = "Stereo dal vivo - Sinistra (SX) - premi 'q' per uscire"
    window_right = "Stereo dal vivo - Destra (DX)"
    for win in (window_left, window_right):
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, 960, 600)

    print("Demo stereo avviata. Premi 'q' o ESC in una delle finestre per uscire.")

    prev_time = time.time()
    try:
        while True:
            ok_l, frame_left = cap_left.read()
            ok_r, frame_right = cap_right.read()
            if not ok_l or not ok_r:
                print("Impossibile leggere un fotogramma da una delle due camere.")
                break

            result = analyzer.analyze_frame_pair(
                timestamp="live", right_img=frame_right, left_img=frame_left, target_label=target_label
            )

            overlay_left = _draw_stereo_overlay(frame_left, result.detections)

            now = time.time()
            fps = 1.0 / max(now - prev_time, 1e-6)
            prev_time = now
            cv2.putText(overlay_left, f"FPS: {fps:.1f}  |  Rilevati: {len(result.detections)}", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            cv2.imshow(window_left, overlay_left)
            cv2.imshow(window_right, frame_right)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        cap_left.release()
        cap_right.release()
        cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo dal vivo: rilevamento YOLO da webcam (mono o stereo).")
    parser.add_argument("--model", type=str, default=None,
                         help="Percorso del modello YOLO (.pt). Default: il primo trovato in models/.")
    parser.add_argument("--mode", type=str, choices=["mono", "stereo"], default="mono",
                         help="'mono' (default): una sola camera, solo rilevamento. "
                              "'stereo': due camere sincronizzate, con misure reali dal vivo.")
    parser.add_argument("--camera", type=int, default=0,
                         help="[modalita' mono] Indice della camera da usare (0 = di solito quella integrata). Default: 0.")
    parser.add_argument("--camera-left", type=int, default=None,
                         help="[modalita' stereo] Indice della camera sinistra (sx) del rig.")
    parser.add_argument("--camera-right", type=int, default=None,
                         help="[modalita' stereo] Indice della camera destra (dx) del rig.")
    parser.add_argument("--class", dest="target_class", type=str, default=DEFAULT_CLASS,
                         help=f"Classe da mostrare (default: '{DEFAULT_CLASS}'). Usa 'all' per mostrare tutte le classi rilevate.")
    parser.add_argument("--list-cameras", action="store_true",
                         help="Elenca le camere disponibili (integrata + eventuali USB esterne) ed esce.")
    args = parser.parse_args()

    if args.list_cameras:
        list_cameras()
        return

    if args.mode == "stereo":
        run_stereo(args)
    else:
        run_mono(args)


if __name__ == "__main__":
    main()
