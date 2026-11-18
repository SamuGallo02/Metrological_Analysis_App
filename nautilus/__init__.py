"""Nautilus underwater image enhancement."""

import os

from .registry import Model, ModelUnavailable, Param, load_models, register

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEIGHTS_DIR = os.environ.get("NAUTILUS_WEIGHTS_DIR", os.path.join(PROJECT_ROOT, "weights"))

__all__ = ["Model", "ModelUnavailable", "Param", "load_models", "register", "PROJECT_ROOT", "WEIGHTS_DIR"]
