"""The metrological analysis run on the server: the same pipeline as the desktop Stereo Analysis page
(corpse.functions.analysis), without the interface. OpenCV, NumPy and Ultralytics are imported only when needed, so the
web pages and the rest of the server work even where they are not installed (the analysis then says it is unavailable).

Unlike the desktop app, the analysis does NOT write label files next to the photos: the library is shared and read-only.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from common.errors import AppError

from .params import MAX_PAIRS, OVERLAY_JPEG_QUALITY, OVERLAY_MAX_SIDE


def _round(v: Optional[float], digits: int = 2) -> Optional[float]:
    return None if v is None else round(float(v), digits)


class AnalysisEngine:
    enhancer = None                              # EnhanceEngine, for "enhance before measuring" (set by the handler)

    def __init__(self) -> None:
        self._lock = threading.Lock()            # one model on the GPU at a time
        self._cached: Optional[Tuple[tuple, Any]] = None
        self._names: Dict[tuple, List[str]] = {}

    # ---- availability -------------------------------------------------------
    @staticmethod
    def status() -> Dict[str, Any]:
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
            from corpse.functions.analysis.analysis import YOLO, select_computation_device
        except ImportError as e:
            return {"available": False, "reason": f"Missing library on the server: {e.name or e}"}
        if YOLO is None:
            return {"available": False, "reason": "Missing library on the server: ultralytics"}
        return {"available": True, "device": select_computation_device()}

    def _require(self) -> None:
        st = self.status()
        if not st["available"]:
            raise AppError("The analysis is not available on this server ({reason}).", 503, reason=st["reason"])

    @staticmethod
    def _model_key(model: Path, cfg: Tuple[float, float, bool]) -> tuple:
        return (str(model), model.stat().st_mtime_ns, cfg)

    # ---- model classes ----------------------------------------------------
    def classes(self, model: Path) -> List[str]:
        self._require()
        key = (str(model), model.stat().st_mtime_ns)
        if key not in self._names:
            from corpse.functions.analysis.analysis import list_model_classes
            with self._lock:
                try:
                    self._names[key] = list_model_classes(str(model))
                except Exception as e:
                    raise AppError("The model could not be loaded: {error}", 422, error=str(e) or type(e).__name__)
        return self._names[key]

    # ---- one analysis -------------------------------------------------------
    def run(self, params: Dict[str, Any], emit: Callable, should_stop: Callable[[], bool],
            set_total: Callable[[int], None]) -> None:
        self._require()
        import cv2
        from corpse.functions.analysis.analysis import ObjectAnalyzer, StereoConfig, render_overlay
        from corpse.functions.analysis.pairing import StereoPairFinder
        from corpse.functions.analysis.tracking import ObjectTracker, generate_adaptive_prefixes

        try:
            pairs = StereoPairFinder(Path(params["_folder"])).scan_and_pair()
        except FileNotFoundError:
            raise AppError("This folder has no lx and rx subfolders: choose a stereo folder.", 422)
        if not pairs:
            raise AppError("No stereo pair found: lx and rx must contain photos with the same names.", 422)
        pairs = pairs[:MAX_PAIRS]
        set_total(len(pairs))

        cfg = StereoConfig(baseline_mm=float(params["baseline_mm"]), focal_length_px=float(params["focal_length_px"]),
                           detect_right=bool(params.get("detect_right", True)))
        model = Path(params["_model_file"])
        with self._lock:
            key = self._model_key(model, (cfg.baseline_mm, cfg.focal_length_px, cfg.detect_right))
            if self._cached is None or self._cached[0] != key:
                self._cached = None                       # frees the previous model first
                try:
                    self._cached = (key, ObjectAnalyzer(str(model), cfg))
                except Exception as e:
                    raise AppError("The model could not be loaded: {error}", 422, error=str(e) or type(e).__name__)
            analyzer = self._cached[1]

            tracker = ObjectTracker()
            seen: set = set()
            label = params.get("label") or None
            enhance = params.get("enhance")              # {"method", "params"}: same correction on both cameras
            for pair in pairs:
                if should_stop():
                    break
                if enhance:
                    right_img, left_img = cv2.imread(str(pair.right_path)), cv2.imread(str(pair.left_path))
                    if right_img is None or left_img is None:
                        raise AppError("The image could not be read.", 422)
                    right_img = self.enhancer.enhance_image(right_img, enhance)
                    left_img = self.enhancer.enhance_image(left_img, enhance)
                    result = analyzer.analyze_frame_pair(pair.timestamp, right_img, left_img, target_label=label)
                else:
                    result = analyzer.analyze_pair(pair.timestamp, pair.right_path, pair.left_path, target_label=label)
                tracker.update(result.detections)
                seen.update(d.label for d in result.detections)
                prefixes = generate_adaptive_prefixes(list(seen))
                for d in result.detections:                    # same ids as the desktop page (e.g. "Pn-3")
                    if d.track_id is not None:
                        num = str(d.track_id).split("-")[-1].split("_")[-1]
                        d.track_id = f"{prefixes.get(d.label, 'Obj')}-{num}"
                overlay = render_overlay(result.left_image, result.detections)
                h, w = overlay.shape[:2]
                scale = min(1.0, OVERLAY_MAX_SIDE / max(h, w))
                if scale < 1.0:
                    overlay = cv2.resize(overlay, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                ok, buf = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, OVERLAY_JPEG_QUALITY])
                emit({"timestamp": pair.timestamp, "width": w, "height": h,
                      "left": pair.left_path.name, "right": pair.right_path.name,
                      "right_detections": len(result.right_detections),
                      "detections": [{
                          "track_id": d.track_id, "label": d.label, "confidence": round(d.confidence, 4),
                          "length_mm": _round(d.length_mm), "width_mm": _round(d.width_mm),
                          "depth_mm": _round(d.depth_mm), "contact_distance_mm": _round(d.contact_distance_mm),
                          "bbox": list(d.bbox_xyxy), "matched_right": d.right_bbox is not None,
                          "disparity_px": _round(d.object_disparity_px)} for d in result.detections]},
                     buf.tobytes() if ok else None, tracker.total_count)
