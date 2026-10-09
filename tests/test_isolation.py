"""Ogni pagina dipende solo da `common` e dai propri file: nessun import tra pagine."""
import ast, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = {"users", "server", "analysis", "training", "manual"}
ALLOWED = {                      # pacchetti del progetto ammessi per ciascuna cartella
    "common": {"common"},
    "users": {"common", "users"},
    "server": {"common", "server"},
    "analysis": {"common", "analysis"},
    "manual": {"common", "manual"},
    "training": {"common", "training", "core", "installer"},     # core/installer: ambiente dell'app (import tardivi)
}
NO_QT = {"server", "common/top"}                                # il server gira senza interfaccia grafica


def imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                yield a.name.split(".")[0], n.lineno
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            yield n.module.split(".")[0], n.lineno
        elif isinstance(n, ast.ImportFrom) and n.level >= 2:        # from ..x : esce dal sotto-pacchetto
            yield "RELATIVE_UP", n.lineno


class TestIsolation(unittest.TestCase):
    def test_no_cross_page_imports(self):
        mine = set(ALLOWED)
        for pkg, allowed in ALLOWED.items():
            for p in (ROOT / pkg).rglob("*.py"):
                for name, line in imports(p):
                    if name in mine and name not in allowed:
                        self.fail(f"{p.relative_to(ROOT)}:{line} imports '{name}' (allowed: {sorted(allowed)})")

    def test_relative_imports_stay_inside_package(self):
        for pkg in ALLOWED:
            for p in (ROOT / pkg).rglob("*.py"):
                tree = ast.parse(p.read_text(encoding="utf-8"))
                depth = len(p.relative_to(ROOT / pkg).parts) - 1          # sotto-cartelle dentro il pacchetto
                for n in ast.walk(tree):
                    if isinstance(n, ast.ImportFrom) and n.level > depth + 1:
                        self.fail(f"{p.relative_to(ROOT)}:{n.lineno} relative import leaves the package")

    def test_server_has_no_gui_dependency(self):
        for p in (ROOT / "server").rglob("*.py"):
            for name, line in imports(p):
                self.assertNotIn(name, ("PySide6", "PyQt5", "PyQt6"), f"{p}:{line}")

    def test_each_page_has_its_params(self):
        for pkg in ("users", "server", "analysis", "training"):
            self.assertTrue((ROOT / pkg / "params.py").is_file(), pkg)
        self.assertTrue((ROOT / "common" / "params.py").is_file())

    def test_ui_and_logic_are_separate(self):
        """La logica (api/session/store/db/storage) non importa Qt."""
        for rel in ("users/api.py", "users/session.py", "users/store.py", "server/db.py", "server/storage.py",
                    "common/security.py", "common/settings.py", "common/i18n.py"):
            for name, line in imports(ROOT / rel):
                self.assertNotEqual(name, "PySide6", f"{rel}:{line}")


if __name__ == "__main__":
    unittest.main()
