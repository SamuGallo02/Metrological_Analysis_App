"""Puts the Nautilus models behind the improvement of the application.

`nautilus` holds the algorithms that clean up an underwater photo (colour cast, haze, contrast), each one with the
settings it takes and a check that says whether it can run on this computer. This module turns each of them into a
method of `common.image_enhance`, so the viewer, the local folders and the worker of the server all use them
without knowing anything about neural networks.

Nothing is imported until it is needed: `nautilus` pulls in OpenCV and PyTorch, which take seconds to load, so
`possible()` only looks whether the libraries are installed, and `install()` does the real work (in a thread, or
when the user opens the improvement window).

    possible()      the libraries are there (cheap, imports nothing)
    install()       imports them and registers the models; returns the names registered
    problems()      model -> why it cannot run here (e.g. its weights were never downloaded)

Autore: Samuele Gallo
"""
from __future__ import annotations

import importlib.util
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from common.image_enhance import is_video, register

NEEDED = ("nautilus", "cv2", "torch")                   # the models; videos also want `av`
VIDEO_CRF = 18                                          # quality of the video that comes out (lower: better)

_lock = threading.Lock()
_installed: List[str] = []
_problems: Dict[str, str] = {}
_done = False


def possible() -> bool:
    """True when the libraries of the models are installed, without importing any of them."""
    return all(importlib.util.find_spec(name) is not None for name in NEEDED)


def video_possible() -> bool:
    return importlib.util.find_spec("av") is not None


def installed() -> List[str]:
    return list(_installed)


def problems() -> Dict[str, str]:
    """The models that are there but cannot run here, with the reason to show the user."""
    return dict(_problems)


def device_name() -> str:
    """The processor or graphics card the models would run on ("" if they cannot run here)."""
    try:
        from nautilus import inference
        return str(inference.device_name())
    except Exception:                                   # noqa: BLE001 - the libraries are missing or broken
        return ""


def install(reload: bool = False) -> List[str]:
    """Registers every Nautilus model as a method of the improvement. Safe to call again: it works once."""
    global _done
    with _lock:
        if _done and not reload:
            return list(_installed)
        _installed.clear()
        _problems.clear()
        _done = True
        if not possible():
            return []
        try:
            from nautilus import load_models
            models = load_models()
        except Exception as e:                          # noqa: BLE001 - a broken installation must not stop the app
            _problems["nautilus"] = str(e)
            return []
        video = video_possible()
        for model in models.values():
            problem = _problem_of(model, video)
            if problem:
                _problems[model.id] = problem
            register(model.id, _runner(model), label=model.name, description=model.description,
                     kind=model.kind, params=[p.to_json() for p in model.params], video=video, problem=problem)
            if not problem:
                _installed.append(model.id)
        return list(_installed)


def _problem_of(model: Any, video: bool) -> str:
    """Why a model cannot be used here: it says so itself (missing weights, no graphics card...)."""
    try:
        return str(model.check() or "")
    except Exception as e:                              # noqa: BLE001 - a check that breaks is a reason as well
        return str(e)


def _runner(model: Any) -> Callable[..., None]:
    """Wraps a model (image in, image out) as a method that reads a file and writes the improved one."""

    def run(src: Path, dst: Path, params: Optional[Dict[str, Any]] = None,
            progress: Optional[Callable[[float], None]] = None) -> None:
        values = model.coerce(params or {})
        if is_video(src):
            _video(src, dst, model, values, progress)
            return
        import cv2
        image = cv2.imread(str(src), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"cannot read the image: {Path(src).name}")
        if progress:
            progress(0.1)
        improved = model.run(image, values)
        if not cv2.imwrite(str(dst), improved):
            raise ValueError(f"cannot write the improved image: {Path(dst).name}")
        if progress:
            progress(1.0)

    return run


def _video(src: Path, dst: Path, model: Any, values: Dict[str, Any],
           progress: Optional[Callable[[float], None]]) -> None:
    """A video is done frame by frame; `nautilus.video` keeps the timing, the audio and the subtitles."""
    if not video_possible():
        raise LookupError("videos need the `av` library")
    from nautilus import video
    length = video.duration(str(src)) or 0.0

    def told(*args: Any, **_kw: Any) -> None:
        """nautilus reports in its own way: only the seconds done are of interest here."""
        if progress and length:
            done = next((a for a in args if isinstance(a, (int, float))), None)
            if done is not None:
                progress(max(0.0, min(1.0, float(done) / length)))

    video.enhance_video(str(src), str(dst), model, values, crf=VIDEO_CRF, progress=told)
