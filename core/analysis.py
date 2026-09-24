"""
Modulo di Analisi Fotogrammetrica e Segmentazione
=================================================

Autore: Samuele Gallo
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Optional, Set

import cv2
import numpy as np

try:
    from ultralytics import YOLO
except ImportError:
    YOLO = None


def select_computation_device() -> str:
    """Determina l'acceleratore hardware ottimale disponibile nel sistema."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def list_model_classes(model_path: str) -> List[str]:
    """Carica un modello YOLO e restituisce l'elenco esatto delle classi conosciute."""
    if YOLO is None:
        raise ImportError("Modulo 'ultralytics' non disponibile nel contesto di esecuzione.")

    model = YOLO(model_path)
    names = model.names
    if isinstance(names, dict):
        return [names[k] for k in sorted(names)]
    return list(names)


def _extract_raw_detections(predictions, timestamp: str) -> List["ObjectDetection"]:
    """
    Estrae le ObjectDetection grezze (contorno, ellisse, classe, confidenza) da
    un risultato di predizione YOLO — SENZA alcuna stima di profondita'/dimensioni
    reali, che richiede una seconda camera e viene aggiunta a parte da chi chiama
    questa funzione quando (e solo quando) una coppia stereo e' disponibile.
    Condivisa da analyze_pair (foto stereo), analyze_single_image (foto singola)
    e ObjectAnalyzer.detect_in_image (un frame video alla volta).
    """
    detections: List[ObjectDetection] = []
    if predictions.masks is None:
        return detections

    for mask_xy, box in zip(predictions.masks.xy, predictions.boxes):
        contour = mask_xy.astype(np.int32).reshape(-1, 1, 2)
        if len(contour) < 5:
            continue

        ellipse = cv2.fitEllipse(contour)
        bbox = tuple(int(v) for v in box.xyxy[0].tolist())
        confidence = float(box.conf[0])
        cls_id = int(box.cls[0])

        class_name = (
            predictions.names.get(cls_id, f"Class_{cls_id}")
            if hasattr(predictions, "names")
            else f"Class_{cls_id}"
        )

        detections.append(ObjectDetection(
            pair_timestamp=timestamp,
            label=class_name,
            confidence=confidence,
            bbox_xyxy=bbox,
            contour=contour,
            ellipse=ellipse,
            length_mm=None,
            width_mm=None,
        ))

    return detections


@dataclass(frozen=True)
class StereoConfig:
    """Parametri geometrici del sistema stereo-fotogrammetrico."""
    baseline_mm: float = 60.0
    focal_length_px: float = 1400.0


@dataclass
class ObjectDetection:
    """Rappresentazione metrologica di un oggetto rilevato."""
    pair_timestamp: str
    label: str
    confidence: float
    bbox_xyxy: Tuple[int, int, int, int]
    contour: np.ndarray
    ellipse: Tuple[Tuple[float, float], Tuple[float, float], float]
    length_mm: Optional[float]
    width_mm: Optional[float]
    depth_mm: Optional[float] = None
    contact_distance_mm: Optional[float] = None  # distanza reale (triangolazione stereo) al punto di contatto/base del soggetto
    track_id: Optional[str] = None  # es. "P-1"


@dataclass
class PairResult:
    """Risultato dell'elaborazione di una coppia di fotogrammi stereo."""
    timestamp: str
    right_image: np.ndarray
    left_image: Optional[np.ndarray] = None
    detections: List[ObjectDetection] = field(default_factory=list)
    overlay_image: Optional[np.ndarray] = None


class ObjectAnalyzer:
    """Pipeline per la rilevazione, segmentazione e misurazione di elementi target."""

    def __init__(
            self,
            model_path: str,
            stereo_config: Optional[StereoConfig] = None,
            device: Optional[str] = None,
    ) -> None:
        if YOLO is None:
            raise ImportError("Modulo 'ultralytics' non disponibile nel contesto di esecuzione.")

        self.device = device or select_computation_device()
        self.model = YOLO(model_path)
        self.stereo_config = stereo_config or StereoConfig()

        # Matcher stereo persistente: creato una sola volta, riusato su ogni coppia.
        # NOTA: presuppone immagini gia' RETTIFICATE (assi ottici paralleli, linee
        # epipolari orizzontali). Con due lenti fissate meccanicamente sullo stesso
        # piano questo e' spesso una buona approssimazione, ma per la massima
        # precisione servirebbe una calibrazione stereo completa (cv2.stereoCalibrate
        # + cv2.stereoRectify) per correggere eventuali disallineamenti/distorsioni
        # residue. Se in futuro avrai le matrici di calibrazione reali, e' qui che
        # andrebbe applicata la rettifica prima del calcolo di disparita'.
        self._stereo_matcher = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=128,
            blockSize=7,
            P1=8 * 3 * 7 ** 2,
            P2=32 * 3 * 7 ** 2,
            disp12MaxDiff=1,
            uniquenessRatio=10,
            speckleWindowSize=100,
            speckleRange=32,
        )

    def _compute_disparity_map(self, left_img: np.ndarray, right_img: np.ndarray) -> Optional[np.ndarray]:
        """Calcola la mappa di disparita' tra le due lenti (sinistra come riferimento)."""
        if self.stereo_config.baseline_mm <= 0 or self.stereo_config.focal_length_px <= 0:
            return None

        gray_left = cv2.cvtColor(left_img, cv2.COLOR_BGR2GRAY)
        gray_right = cv2.cvtColor(right_img, cv2.COLOR_BGR2GRAY)

        raw_disparity = self._stereo_matcher.compute(gray_left, gray_right)
        return raw_disparity.astype(np.float32) / 16.0  # StereoSGBM restituisce disparita' in fixed-point 4 bit

    def _depth_from_disparity(
            self,
            disparity_map: Optional[np.ndarray],
            x: int,
            y: int,
            window: int = 3,
    ) -> Optional[float]:
        """
        Stima la profondita' reale (mm) nel punto (x, y) dell'immagine sinistra
        tramite triangolazione: depth = (baseline_mm * focal_length_px) / disparita'.
        Campiona una piccola finestra attorno al punto (mediana) per robustezza
        al rumore locale della corrispondenza stereo.
        """
        if disparity_map is None:
            return None

        h, w = disparity_map.shape
        x0, x1 = max(0, x - window), min(w, x + window + 1)
        y0, y1 = max(0, y - window), min(h, y + window + 1)
        region = disparity_map[y0:y1, x0:x1]

        valid = region[region > 0]  # disparita' <= 0 = corrispondenza non trovata/non valida
        if valid.size == 0:
            return None

        disparity_px = float(np.median(valid))
        return (self.stereo_config.baseline_mm * self.stereo_config.focal_length_px) / disparity_px

    def _get_scale_factor(self, depth_mm: Optional[float]) -> Optional[float]:
        """
        Ritorna il fattore mm/px da applicare alle dimensioni in pixel, oppure
        None se non c'e' una profondita' stereo valida in quel punto — MAI un
        fallback approssimato, che introdurrebbe errore proporzionale a quanto
        il soggetto e' realmente distante dall'assunzione implicita.
        """
        cfg = self.stereo_config
        if depth_mm and cfg.focal_length_px:
            return depth_mm / cfg.focal_length_px
        return None

    def analyze_pair(
            self,
            timestamp: str,
            right_path: Path,
            left_path: Path,
            target_label: Optional[str] = None,
    ) -> PairResult:
        """
        Legge una coppia di immagini stereo da disco ed esegue analyze_frame_pair.
        """
        right_img = cv2.imread(str(right_path))
        left_img = cv2.imread(str(left_path))

        if right_img is None or left_img is None:
            raise FileNotFoundError(f"Errore nella lettura dei file: {right_path} o {left_path}")

        return self.analyze_frame_pair(timestamp, right_img, left_img, target_label=target_label)

    def analyze_frame_pair(
            self,
            timestamp: str,
            right_img: np.ndarray,
            left_img: np.ndarray,
            target_label: Optional[str] = None,
    ) -> PairResult:
        """
        Esegue l'intera pipeline stereo (disparita' + rilevamento + misure) su una
        coppia di immagini GIA' IN MEMORIA. Usata sia da analyze_pair (immagini
        lette da disco) sia dall'analisi video-stereo (fotogrammi letti da due
        VideoCapture sincronizzati) — la logica di misura e' quindi UNA sola,
        condivisa da entrambi i percorsi, invece di essere duplicata.
        Esegue la rilevazione sulla CAMERA SINISTRA (lx).
        """
        result = PairResult(timestamp=timestamp, right_image=right_img, left_image=left_img)

        # Mappa di disparita' calcolata UNA volta per coppia (non per rilevamento):
        # e' l'operazione piu' costosa, va riusata per tutti i soggetti del frame.
        disparity_map = self._compute_disparity_map(left_img, right_img)

        # Predict eseguito su LEFT_IMG
        predictions = self.model.predict(left_img, device=self.device, verbose=False)[0]
        target_label_lower = target_label.strip().lower() if target_label else None

        for detection in _extract_raw_detections(predictions, timestamp):
            if target_label_lower is not None and detection.label.strip().lower() != target_label_lower:
                continue

            bbox = detection.bbox_xyxy
            _, (major_px, minor_px), _ = detection.ellipse

            depth_mm = self._depth_from_disparity(
                disparity_map, (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
            )
            scale = self._get_scale_factor(depth_mm)
            detection.length_mm = major_px * scale if scale is not None else None
            detection.width_mm = minor_px * scale if scale is not None else None
            detection.depth_mm = depth_mm

            # Distanza al punto di contatto: profondita' REALE (triangolazione
            # stereo) nel punto in cui il soggetto tocca la superficie sottostante
            # (base del bounding box). Se la corrispondenza stereo non riesce in
            # quel punto (es. zona poco tessiturizzata), resta None: nessuna
            # stima geometrica di ripiego, per non introdurre errore da un
            # angolo di inclinazione difficile da misurare con precisione.
            detection.contact_distance_mm = self._depth_from_disparity(
                disparity_map, (bbox[0] + bbox[2]) // 2, bbox[3]
            )

            result.detections.append(detection)

        return result

    def detect_in_image(self, image: np.ndarray, timestamp: str) -> List[ObjectDetection]:
        """
        Rileva e segmenta i soggetti in una singola immagine gia' in memoria
        (usato dal flusso video, un frame alla volta). Nessuna stima di
        profondita'/dimensioni reali: qui non c'e' una seconda camera con cui
        triangolare, esattamente come per l'analisi di una foto singola.
        """
        predictions = self.model.predict(image, device=self.device, verbose=False)[0]
        return _extract_raw_detections(predictions, timestamp)


def analyze_single_image(model_path: str, image_path: Path) -> Tuple[np.ndarray, List[ObjectDetection]]:
    """
    Rileva e segmenta i soggetti in una singola foto (nessuna stereo-coppia
    disponibile): nessuna stima di profondita'/dimensioni reali, solo
    maschera, classe e confidenza. Carica il modello una sola volta per
    l'intera chiamata (uso occasionale, a differenza del flusso video che
    riusa un ObjectAnalyzer gia' istanziato su molti frame).
    """
    if YOLO is None:
        raise ImportError("Modulo 'ultralytics' non disponibile nel contesto di esecuzione.")

    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Errore nella lettura del file immagine: {image_path}")

    model = YOLO(model_path)
    device = select_computation_device()
    predictions = model.predict(image, device=device, verbose=False)[0]

    detections = _extract_raw_detections(predictions, timestamp=Path(image_path).stem)
    return image, detections


def render_overlay(
    image: np.ndarray,
    detections: List[ObjectDetection],
    filter_ids: Optional[Set[str]] = None
) -> np.ndarray:
    """
    Disegna maschere ed etichette. Se filter_ids è fornito, mostra SOLO
    gli oggetti aventi track_id presente in filter_ids.
    """
    overlay = image.copy()

    for detection in detections:
        if filter_ids is not None and detection.track_id not in filter_ids:
            continue

        cv2.drawContours(overlay, [detection.contour], -1, (0, 255, 0), 2)
        cv2.ellipse(overlay, detection.ellipse, (0, 165, 255), 2)

        id_str = f"[{detection.track_id}] " if detection.track_id else ""
        caption = f"{id_str}{detection.label}"

        # Sfondo nero per rendere la scritta sempre ben visibile
        txt_size, _ = cv2.getTextSize(caption, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        tx, ty = detection.bbox_xyxy[0], max(detection.bbox_xyxy[1] - 8, 20)
        cv2.rectangle(overlay, (tx, ty - txt_size[1] - 4), (tx + txt_size[0] + 4, ty + 4), (0, 0, 0), -1)

        cv2.putText(
            overlay,
            caption,
            (tx + 2, ty),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

    return overlay