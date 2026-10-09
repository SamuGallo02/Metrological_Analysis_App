"""Integrity check of the virtual environment (common/ambient/installer/integrity.py)."""
import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from common.ambient.installer import integrity


def make_venv(root: Path, files: dict) -> Path:
    """Fake venv with one package `demo 1.0` whose RECORD lists `files`."""
    sp = root / "Lib" / "site-packages"
    info = sp / "demo-1.0.dist-info"
    info.mkdir(parents=True)
    rows = []
    for rel, data in files.items():
        (sp / rel).parent.mkdir(parents=True, exist_ok=True)
        (sp / rel).write_bytes(data)
        h = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        rows.append(f"{rel},sha256={h},{len(data)}")
    rows += ["demo-1.0.dist-info/RECORD,,", "../../Scripts/demo.exe,sha256=x,5", "demo/__pycache__/a.pyc,sha256=x,5"]
    (info / "RECORD").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return root


class TestIntegrity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.venv = make_venv(self.tmp, {"demo/__init__.py": b"x = 1\n", "demo/big.dll": b"A" * 5000})
        self.sp = self.venv / "Lib" / "site-packages"

    def test_healthy(self):
        self.assertEqual(integrity.scan(self.venv), {})
        self.assertEqual(integrity.scan(self.venv, deep=True), {})

    def test_truncated_and_missing(self):
        (self.sp / "demo/big.dll").write_bytes(b"A" * 100)           # cut short (disk full)
        d = integrity.scan(self.venv)["demo"]
        self.assertEqual((d.version, d.files), ("1.0", ["demo/big.dll"]))
        (self.sp / "demo/__init__.py").unlink()
        self.assertEqual(sorted(integrity.scan(self.venv)["demo"].files), ["demo/__init__.py", "demo/big.dll"])

    def test_same_size_corruption_needs_deep(self):
        (self.sp / "demo/big.dll").write_bytes(b"B" * 5000)
        self.assertEqual(integrity.scan(self.venv), {})                # sizes are equal: quick scan cannot see it
        self.assertEqual(integrity.scan(self.venv, deep=True)["demo"].files, ["demo/big.dll"])

    def test_torch_index_from_version(self):
        self.assertTrue(integrity.torch_index("2.6.0+cu126").endswith("/whl/cu126"))
        self.assertIsNone(integrity.torch_index("2.6.0"))

    def test_startup_check_ignores_other_environments(self):
        self.assertEqual(integrity.startup_check(), {})                # not the project venv: nothing is checked

    def test_touches_qt(self):
        d = integrity.Damage("PySide6-Essentials", "6.8", ["x"])
        self.assertTrue(integrity.touches_qt({"pyside6-essentials": d}))
        self.assertFalse(integrity.touches_qt({"torch": integrity.Damage("torch", "2", ["y"])}))


if __name__ == "__main__":
    unittest.main()
