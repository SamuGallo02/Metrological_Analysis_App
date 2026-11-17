"""What a normal user gets at installation: only the minimum (connect to the server and analyse).
Everything else — GPU training above all — is installed later, on request."""
import unittest
from pathlib import Path

from common.ambient.installer import plan
from common.ambient.installer.sysinfo import OS_LINUX, OS_MACOS, OS_WINDOWS, SystemInfo


def info(os_name, **kw):
    return SystemInfo(os_name=os_name, arch="x86_64", python=(3, 12, 0), **kw)

REQS = Path(__file__).resolve().parent.parent / "common" / "ambient" / "requirements"
# Everything in this list must stay needed to open the app, talk to the server and run an analysis.
CORE = {"PySide6", "opencv-python", "numpy", "pandas", "ultralytics"}


def names(path: Path):
    return {ln.split(">")[0].split("=")[0].split("[")[0].strip()
            for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")}


class CoreInstallTest(unittest.TestCase):
    def test_the_core_requirements_do_not_grow_by_accident(self):
        self.assertEqual(names(REQS / "requirements.txt"), CORE)

    def test_the_gpu_build_of_pytorch_is_never_installed_on_its_own(self):
        for os_name in (OS_WINDOWS, OS_LINUX, OS_MACOS):
            system = info(os_name, nvidia=True, gpu_name="RTX 4090", driver_cuda=(12, 6))
            self.assertNotEqual(plan.core_torch(system).label[:2], "cu", os_name)      # cpu or default, never cu126
        self.assertEqual(plan.core_torch(info(OS_MACOS)).label, "default")

    def test_the_cuda_build_is_only_offered_with_an_nvidia_gpu(self):
        self.assertEqual(plan.training_torch_candidates(info(OS_WINDOWS, nvidia=False)), [])
        self.assertEqual(plan.training_torch_candidates(info(OS_MACOS, nvidia=True)), [])
        best = plan.training_torch_candidates(info(OS_WINDOWS, nvidia=True, driver_cuda=(12, 6)))
        self.assertEqual(best[0].label, "cu126")

    def test_nothing_is_needed_for_training_without_a_gpu(self):
        needed, why = plan.training_needed(info(OS_WINDOWS, nvidia=False))
        self.assertFalse(needed)
        self.assertTrue(why)
        self.assertFalse(plan.training_needed(info(OS_MACOS))[0])

    def test_the_training_extras_stay_out_of_the_core(self):
        self.assertFalse(names(REQS / "requirements-training.txt") & CORE)


if __name__ == "__main__":
    unittest.main()
