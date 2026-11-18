"""Running the neural networks, on the best device available.

``NAUTILUS_DEVICE`` picks the device (default ``auto``):

    auto            first match of: NVIDIA/AMD GPU (PyTorch CUDA/ROCm), Intel GPU (PyTorch XPU),
                    Intel integrated GPU through OpenVINO (e.g. Intel N95/N100 mini PCs),
                    Apple GPU (MPS), CPU through OpenVINO, then CPU through PyTorch
    cpu, cuda, xpu, mps          that PyTorch device
    openvino, openvino:GPU       OpenVINO on the GPU (needs `pip install openvino`)
    openvino:CPU                 OpenVINO on the CPU

If a network fails on the GPU (e.g. out of memory on a large image), that image is
retried on the CPU, so a job never fails only because of the GPU.
"""

import logging
import os
import subprocess
import sys
import threading

import numpy as np

# AMD GPUs (ROCm): by default MIOpen benchmarks every convolution algorithm the first time it
# sees an image size, which takes minutes for photos of several megapixels. FAST mode picks
# one from its heuristics instead (as fast in practice); sizes already tuned are still reused.
os.environ.setdefault("MIOPEN_FIND_MODE", "FAST")

import torch  # noqa: E402

log = logging.getLogger("nautilus")

# Full-resolution CNNs are memory hungry: run one network at a time per process.
inference_lock = threading.Lock()

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "nautilus", "openvino")


def _openvino_core():
    try:
        import openvino as ov
    except ImportError:
        return None
    return ov.Core()


_PROBE = """
import sys, numpy as np, openvino as ov, openvino.opset13 as ops
x = ops.parameter([1, 3, 32, 32], np.float32)
w = ops.constant(np.ones((4, 3, 3, 3), np.float32))
model = ov.Model([ops.convolution(x, w, [1, 1], [1, 1], [1, 1], [1, 1])], [x])
out = ov.Core().compile_model(model, sys.argv[1])(np.ones((1, 3, 32, 32), np.float32))[0]
assert abs(float(out[0, 0, 5, 5]) - 27) < 0.1
"""


def _openvino_gpu_works(device):
    """Run a tiny network on the GPU in a separate process, so a driver crash can't take the server down."""
    try:
        result = subprocess.run([sys.executable, "-c", _PROBE, device], capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        log.warning("OpenVINO %s failed a self-test, using the CPU instead:\n%s", device,
                    result.stderr.decode(errors="replace")[-500:])
    return result.returncode == 0


def _pick_device():
    wanted = os.environ.get("NAUTILUS_DEVICE", "auto").strip()
    if wanted.startswith("openvino"):
        core = _openvino_core()
        if core is None:
            raise RuntimeError("NAUTILUS_DEVICE=openvino needs OpenVINO: pip install openvino")
        return ("openvino", wanted.partition(":")[2] or "GPU")
    if wanted != "auto":
        return ("torch", wanted)

    if torch.cuda.is_available():
        return ("torch", "cuda")
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        return ("torch", "xpu")
    core = _openvino_core()
    if core is not None:
        for dev in (d for d in core.available_devices if d.startswith("GPU")):
            # OpenVINO's GPU kernels are written for Intel GPUs; on other GPUs it can crash the process.
            if "intel" in core.get_property(dev, "FULL_DEVICE_NAME").lower() and _openvino_gpu_works(dev):
                return ("openvino", dev)
    if torch.backends.mps.is_available():
        return ("torch", "mps")
    if core is not None:
        # About 2.5x faster than PyTorch on the CPU for these networks.
        return ("openvino", "CPU")
    return ("torch", "cpu")


BACKEND, DEVICE = _pick_device()


def device_name():
    """Human-readable name of the device the networks run on."""
    try:
        if BACKEND == "openvino":
            return _openvino_core().get_property(DEVICE, "FULL_DEVICE_NAME").strip()
        if DEVICE.startswith("cuda"):
            return torch.cuda.get_device_name()
        if DEVICE.startswith("xpu"):
            return torch.xpu.get_device_name()
    except Exception:  # noqa: BLE001 - only used for display
        pass
    return {"cpu": "CPU", "mps": "Apple GPU"}.get(DEVICE, DEVICE)


def uses_gpu():
    return DEVICE.lower() != "cpu"


def to_nchw(arr):
    """HWC uint8 image -> 1CHW float32 array in [0, 1]."""
    return (np.ascontiguousarray(arr.transpose(2, 0, 1))[None] / np.float32(255)).astype(np.float32)


def from_nchw(arr):
    """1CHW float array in [0, 1] -> HWC uint8 image."""
    return (np.clip(arr[0].transpose(1, 2, 0), 0, 1) * 255).astype(np.uint8)


class Network:
    """A network whose weights are loaded on first use, on the selected device.

    Call it with 1CHW float32 numpy arrays; it returns a 1CHW float32 numpy array.
    """

    def __init__(self, path, build, download_url=None):
        self.path = path
        self.build = build
        self.download_url = download_url
        self._torch = None     # model on the CPU (also the fallback)
        self._device = None    # model on the selected device (torch module or compiled OpenVINO model)
        self._lock = threading.Lock()

    def check(self):
        if os.path.exists(self.path):
            return None
        hint = f" Download it from {self.download_url}" if self.download_url else ""
        return f"Not installed on this computer: the file {os.path.relpath(self.path)} is missing.{hint}"

    def load(self):
        with self._lock:
            if self._torch is not None:
                return
            model = self.build()
            model.load_state_dict(torch.load(self.path, map_location="cpu", weights_only=True))
            self._torch = model.eval()
            try:
                self._device = self._to_device(self._torch)
            except Exception:  # noqa: BLE001
                log.exception("Could not load %s on %s; using the CPU", os.path.basename(self.path), DEVICE)
                self._device = None

    def _to_device(self, model):
        if BACKEND == "openvino":
            import openvino as ov

            core = _openvino_core()
            os.makedirs(CACHE_DIR, exist_ok=True)
            core.set_property({"CACHE_DIR": CACHE_DIR})  # compiled kernels are reused across restarts
            n_inputs = model.forward.__code__.co_argcount - 1
            example = tuple(torch.rand(1, 3, 64, 64) for _ in range(n_inputs))
            # Height and width stay dynamic, so any image size works with one conversion.
            converted = ov.convert_model(model, example_input=example, input=[[1, 3, -1, -1]] * n_inputs)
            return core.compile_model(converted, DEVICE)
        if DEVICE == "cpu":
            return None
        return model.to(DEVICE)

    def __call__(self, *inputs):
        self.load()
        with inference_lock:
            if self._device is not None:
                try:
                    return self._run_device(inputs)
                except Exception as e:  # noqa: BLE001
                    log.warning("%s failed on %s (%s); retrying on the CPU", os.path.basename(self.path), DEVICE, e)
                    if DEVICE.startswith("cuda"):
                        torch.cuda.empty_cache()
            with torch.no_grad():
                return self._torch(*(torch.from_numpy(x) for x in inputs)).numpy()

    def _run_device(self, inputs):
        if BACKEND == "openvino":
            request = self._device.create_infer_request()
            request.infer(list(inputs))
            return request.get_output_tensor(0).data.copy()
        with torch.no_grad():
            out = self._device(*(torch.from_numpy(x).to(DEVICE) for x in inputs))
            return out.float().cpu().numpy()
