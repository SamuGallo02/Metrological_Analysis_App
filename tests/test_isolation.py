"""Each section depends only on `common` and its own files: no imports between sections (except the home, which connects them)."""
import ast, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = ("analysis", "home", "training", "users", "manual")


def section_dirs():
    """(name, folder) of each independent section."""
    out = [("common", ROOT / "common"), ("server", ROOT / "server")]
    for s in SECTIONS:
        for kind in ("functions", "gui"):
            d = ROOT / "corpse" / kind / s
            if d.is_dir():
                out.append((f"corpse.{kind}.{s}", d))
    return out


def imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                yield a.name, n.lineno
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            yield n.module, n.lineno


def allowed(name: str, module: str) -> bool:
    """Can module `module` be imported by code in section `name`?"""
    top = module.split(".")[0]
    if top not in ("common", "corpse", "server"):
        return True                                            # external or standard library
    if name == "server":
        return top in ("common", "server")
    if name == "common":
        return top == "common"
    _, kind, section = name.split(".")                         # corpse.<functions|gui>.<section>
    if top == "common":
        return True
    if section == "home" and kind == "gui":
        return top == "corpse"                                 # the home connects all sections
    own_f = f"corpse.functions.{section}"
    own_g = f"corpse.gui.{section}"
    if kind == "functions":
        return module == own_f or module.startswith(own_f + ".")
    return any(module == m or module.startswith(m + ".") for m in (own_f, own_g))


class TestIsolation(unittest.TestCase):
    def test_no_cross_section_imports(self):
        for name, d in section_dirs():
            for p in d.rglob("*.py"):
                for module, line in imports(p):
                    if not allowed(name, module):
                        self.fail(f"{p.relative_to(ROOT)}:{line} imports '{module}' (not allowed for {name})")

    def test_relative_imports_stay_inside_section(self):
        for name, d in section_dirs():
            for p in d.rglob("*.py"):
                tree = ast.parse(p.read_text(encoding="utf-8"))
                depth = len(p.relative_to(d).parts) - 1
                for n in ast.walk(tree):
                    if isinstance(n, ast.ImportFrom) and n.level > depth + 1:
                        self.fail(f"{p.relative_to(ROOT)}:{n.lineno} relative import leaves the section")

    def test_server_has_no_gui_dependency(self):
        for p in (ROOT / "server").rglob("*.py"):
            for module, line in imports(p):
                self.assertNotIn(module.split(".")[0], ("PySide6", "PyQt5", "PyQt6"), f"{p}:{line}")

    def test_each_section_has_its_params(self):
        for rel in ("server/params.py", "common/params.py", "corpse/functions/users/params.py",
                    "corpse/functions/training/params.py", "corpse/functions/home/hub_params.py"):
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_logic_never_imports_qt(self):
        """The `functions` folders and the server do not import Qt: logic is kept separate from the interface."""
        files = list((ROOT / "corpse" / "functions").rglob("*.py")) + [
            ROOT / "server" / "db.py", ROOT / "server" / "storage.py", ROOT / "common" / "security" / "security.py",
            ROOT / "common" / "settings" / "settings.py", ROOT / "common" / "i18n.py"]
        files = [f for f in files if f.name != "worker.py"]         # the training worker is a QThread: it uses Qt
        for p in files:
            for module, line in imports(p):
                self.assertNotEqual(module.split(".")[0], "PySide6", f"{p.relative_to(ROOT)}:{line}")


if __name__ == "__main__":
    unittest.main()
