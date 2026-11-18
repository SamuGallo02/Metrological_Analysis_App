"""Underwater image enhancement for the web app, with the `nautilus` core (WaterNet, FUnIE-GAN, fusion...).

* preview(): the chosen methods on a reduced copy of one photo (or one frame of a video), in a few seconds;
* run(): a background job (webapp.jobs) on a photo, a video or a whole folder at full size. The results are written
  next to the originals (see the handler), with the same names, so stereo pairs (lx/rx) and YOLO labels still match:
  the enhancement changes the colours, never the geometry, so the label files are copied unchanged;
* enhance_image(): used by the analysis ("enhance before measuring").

PyTorch, OpenCV and the networks are imported only when needed: without them the rest of the web app works and the
page says what is missing.
"""
from __future__ import annotations

import base64
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from common.errors import AppError
from common.params import IMAGE_SUFFIXES, LABEL_SUFFIX, VIDEO_SUFFIXES

PREVIEW_SIZE = int(os.environ.get("NAUTILUS_PREVIEW_SIZE", 1280))
PREVIEW_JPEG = 88
VIDEO_CRF = int(os.environ.get("NAUTILUS_VIDEO_CRF", 18))
MAX_PREVIEW_METHODS = 6
PNG_OUTPUT = {".png", ".tif", ".tiff", ".bmp"}           # lossless originals stay lossless (as PNG)
COPIED = {LABEL_SUFFIX, ".yaml", ".yml", ".json", ".ass", ".srt"}   # labels, classes, data.yaml, subtitles


def media_kind(path: Path) -> Optional[str]:
    ext = path.suffix.lower()
    return "image" if ext in IMAGE_SUFFIXES else "video" if ext in VIDEO_SUFFIXES else None


def output_name(path: Path) -> str:
    """Enhanced file name: same stem (pairs and labels still match), PNG for lossless originals, MP4 for videos."""
    kind, ext = media_kind(path), path.suffix.lower()
    if kind == "video":
        return path.stem + ".mp4"
    return path.stem + (".png" if ext in PNG_OUTPUT else ext)


class EnhanceEngine:
    def __init__(self) -> None:
        self._models = None
        self._lock = threading.Lock()

    # ---- availability --------------------------------------------------------
    def _load(self):
        if self._models is None:
            with self._lock:
                if self._models is None:
                    from nautilus import load_models
                    self._models = load_models()
        return self._models

    def status(self) -> Dict[str, Any]:
        try:
            import cv2  # noqa: F401
            import torch  # noqa: F401
            models = self._load()
            from nautilus import inference
        except ImportError as e:
            return {"available": False, "reason": f"Missing library on the server: {e.name or e}", "methods": []}
        try:
            import av  # noqa: F401
            video = True
        except ImportError:
            video = False
        return {"available": True, "device": inference.device_name(), "gpu": inference.uses_gpu(), "video": video,
                "methods": [m.to_json() for m in models.values()]}

    def _require(self) -> Dict[str, Any]:
        st = self.status()
        if not st["available"]:
            raise AppError("Image enhancement is not available on this server ({reason}).", 503, reason=st["reason"])
        return st

    def check_method(self, method: Any, params: Any) -> Dict[str, Any]:
        """{"method", "params"} checked: a known, installed method and its settings within their limits."""
        self._require()
        model = self._load().get(str(method or ""))
        if model is None:
            raise AppError("Unknown enhancement method.", 422)
        problem = model.check()
        if problem:
            raise AppError("This enhancement method is not installed on the server.", 422)
        try:
            values = model.coerce(params if isinstance(params, dict) else {})
        except (TypeError, ValueError) as e:
            raise AppError("Invalid setting: {error}", 422, error=str(e))
        return {"method": model.id, "params": values}

    # ---- single images -----------------------------------------------------------
    def enhance_image(self, image, method: Dict[str, Any]):
        return self._load()[method["method"]].run(image, method["params"])

    @staticmethod
    def _read(path: Path, seconds: float = 0.0):
        import cv2
        if media_kind(path) == "video":
            from nautilus import video
            frame = video.read_frame(str(path), max(0.0, seconds))
            if frame is None:
                raise AppError("This video is shorter than that.", 422)
            return frame, video.duration(str(path))
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise AppError("The image could not be read.", 422)
        return image, None

    @staticmethod
    def _jpeg(image) -> str:
        import cv2
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, PREVIEW_JPEG])
        return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")

    def preview(self, path: Path, methods: List[Dict[str, Any]], seconds: float = 0.0) -> Dict[str, Any]:
        """The original and each method on a copy at most PREVIEW_SIZE pixels on its long side."""
        import cv2
        from nautilus.metrics import compute
        self._require()
        if media_kind(path) is None:
            raise AppError("Choose a photo or a video.", 422)
        if not methods or len(methods) > MAX_PREVIEW_METHODS:
            raise AppError("Choose from 1 to {n} methods.", 422, n=MAX_PREVIEW_METHODS)
        checked = [self.check_method(m.get("id") if isinstance(m, dict) else m,
                                     m.get("params") if isinstance(m, dict) else None) for m in methods]
        image, duration = self._read(path, seconds)
        h, w = image.shape[:2]
        scale = min(1.0, PREVIEW_SIZE / max(h, w))
        if scale < 1:
            image = cv2.resize(image, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        out = {"width": w, "height": h, "duration": duration, "seconds": seconds,
               "original": {"image": self._jpeg(image), "metrics": compute(image)}, "results": []}
        for m in checked:
            began = time.perf_counter()
            try:
                result = self.enhance_image(image, m)
                out["results"].append({"id": m["method"], "params": m["params"], "image": self._jpeg(result),
                                       "metrics": compute(result), "seconds": round(time.perf_counter() - began, 2)})
            except Exception as e:                                    # one method failing must not hide the others
                out["results"].append({"id": m["method"], "params": m["params"], "error": str(e) or type(e).__name__})
        return out

    # ---- background job -------------------------------------------------------------
    def run(self, params: Dict[str, Any], emit: Callable, should_stop: Callable[[], bool],
            set_total: Callable[[int], None], progress: Callable[[float], None] = lambda f: None) -> None:
        """params: _source (file or folder), _output (file or folder), _quota_root, _quota_bytes, method, params."""
        import cv2
        from nautilus.metrics import compute
        st = self._require()
        method = {"method": params["method"], "params": params["params"]}
        model = self._load()[method["method"]]
        src, dst = Path(params["_source"]), Path(params["_output"])
        quota = Quota(Path(params["_quota_root"]), int(params["_quota_bytes"]))

        if src.is_file():
            items = [(src, dst)]
            extras: List[tuple] = []
        else:
            items, extras = [], []
            exclude = [Path(e) for e in params.get("_exclude") or ()]
            for p in sorted(src.rglob("*")):
                if not p.is_file() or any(part.startswith(".") for part in p.relative_to(src).parts):
                    continue
                if any(p == e or e in p.parents for e in exclude):
                    continue                                   # hidden from the user who started the job
                rel = p.relative_to(src)
                if media_kind(p):
                    items.append((p, dst / rel.parent / output_name(p)))
                elif p.suffix.lower() in COPIED or p.name == "classes.txt":
                    extras.append((p, dst / rel))
        if not items:
            raise AppError("No photo or video to enhance here.", 422)
        if any(media_kind(p) == "video" for p, _ in items) and not st["video"]:
            raise AppError("Videos cannot be enhanced on this server (missing library: av).", 503)
        set_total(len(items))
        for p, target in extras:                       # labels and settings files: unchanged, next to their media
            quota.reserve(p.stat().st_size)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
        for p, target in items:
            if should_stop():
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            began = time.perf_counter()
            row: Dict[str, Any] = {"file": str(p.relative_to(src)) if src.is_dir() else p.name,
                                   "output": str(target.relative_to(dst)) if src.is_dir() else target.name}
            if media_kind(p) == "image":
                image = cv2.imread(str(p), cv2.IMREAD_COLOR)
                if image is None:
                    row["error"] = "The image could not be read."
                    emit(row, None, 0)
                    continue
                result = self.enhance_image(image, method)
                ext = target.suffix.lower()
                ok, buf = cv2.imencode(ext, result, [cv2.IMWRITE_JPEG_QUALITY, 95] if ext in (".jpg", ".jpeg") else [])
                if not ok:
                    raise AppError("The image could not be written.", 500)
                quota.reserve(len(buf))
                tmp = target.with_name("." + target.name + ".part")
                tmp.write_bytes(buf.tobytes())
                os.replace(tmp, target)
                row["metrics"] = compute(result)
            else:
                from nautilus import video

                def report(done, total):
                    if should_stop():
                        raise _Stopped()
                    if total:
                        progress(min(1.0, done / total))
                tmp = target.with_name("." + target.stem + ".part.mp4")
                try:
                    row["frames"] = video.enhance_video(str(p), str(tmp), model, method["params"], crf=VIDEO_CRF,
                                                        progress=lambda line: None, report=report)
                except _Stopped:
                    return
                quota.reserve(tmp.stat().st_size, tmp)
                os.replace(tmp, target)
                video.copy_subtitles(str(p), str(target))
            row["seconds"] = round(time.perf_counter() - began, 2)
            emit(row, None, 0)


class _Stopped(Exception):
    pass


class Quota:
    """Space left in the folder the results go to (personal folder or folder of a work group): checked before each file is kept."""

    def __init__(self, root: Path, limit: int):
        self.limit = limit
        self.used = sum(p.stat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink()) \
            if root.exists() else 0

    def reserve(self, size: int, cleanup: Optional[Path] = None) -> None:
        if self.used + size > self.limit:
            if cleanup is not None:
                cleanup.unlink(missing_ok=True)
            raise AppError("Not enough space for the results (quota {mb} MB).", 413, mb=self.limit >> 20)
        self.used += size


class Engines:
    """What the job queue runs: an analysis or an enhancement, by params["type"]."""

    def __init__(self, analysis, enhance):
        self.analysis, self.enhance = analysis, enhance

    def run(self, params, emit, should_stop, set_total, **kw):
        if params.get("type") == "enhance":
            return self.enhance.run(params, emit, should_stop, set_total, **kw)
        return self.analysis.run(params, emit, should_stop, set_total)
