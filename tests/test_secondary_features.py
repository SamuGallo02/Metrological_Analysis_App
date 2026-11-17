"""All the buttons are there from the first start: the ones that need something downloaded say so when pressed,
without blocking the application. And no process of the application ever opens a console window.

Autore: Samuele Gallo
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QWidget        # noqa: E402

from common.ambient.no_console import CREATE_NEW_CONSOLE, CREATE_NO_WINDOW, DETACHED_PROCESS, hidden_flags  # noqa: E402
from common.ui.widgets import open_performance, performance_available, set_performance_opener  # noqa: E402

app = QApplication.instance() or QApplication([])


class NoConsoleTest(unittest.TestCase):
    def test_a_normal_process_is_asked_for_without_a_console(self):
        self.assertEqual(hidden_flags(0), CREATE_NO_WINDOW)
        self.assertEqual(hidden_flags(0x200), 0x200 | CREATE_NO_WINDOW)

    def test_a_process_that_wants_its_own_console_is_left_alone(self):
        # Windows refuses a process asked for with both: the detached ones (installer, restart) keep their flags.
        for flag in (DETACHED_PROCESS, CREATE_NEW_CONSOLE, DETACHED_PROCESS | 0x200):
            self.assertEqual(hidden_flags(flag), flag)

    def test_every_process_of_the_application_hides_the_console(self):
        """Nothing in the code may start a process without saying how it must appear."""
        import re
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        call = re.compile(r"subprocess\.(Popen|run|call|check_output|check_call)\s*\(")
        bad = []
        for f in sorted(list((root / "common").rglob("*.py")) + list((root / "corpse").rglob("*.py"))):
            if "__pycache__" in f.parts:
                continue
            s = f.read_text(encoding="utf-8", errors="replace")
            for m in call.finditer(s):
                i, depth = m.end(), 1
                while i < len(s) and depth:
                    depth += (s[i] == "(") - (s[i] == ")")
                    i += 1
                text = s[m.start():i]
                if re.search(r"NOWIN|NO_WINDOW|DETACHED|creationflags|start_new_session", text):
                    continue
                if re.search(r'"(open|xdg-open|osascript|notify-send)"', text):
                    continue                                        # macOS and Linux: there is no console there
                bad.append(f"{f.relative_to(root)}:{s[:m.start()].count(chr(10)) + 1}")
        self.assertEqual(bad, [], "processes started without hiding the console: " + ", ".join(bad))


class SecondaryFeaturesTest(unittest.TestCase):
    def test_the_training_page_opens_without_the_components(self):
        """The home must not install anything to show the page: on the server one trains with nothing local."""
        import inspect
        from corpse.gui.home import home_gui
        source = inspect.getsource(home_gui.AppWindow._open_training)
        self.assertIn("show_page", source)
        self.assertNotIn("ensure_training_ready", source)

    def test_the_components_window_does_not_block_the_application(self):
        from corpse.gui.training import setup_dialog
        status = {"install_needed": False, "extras_pending": True, "install_variant": "cu126", "gpu_name": ""}
        dlg = setup_dialog.TrainingSetupDialog(status)
        dlg.setModal(False)
        dlg.show()
        self.assertFalse(dlg.isModal())                             # the rest of the app stays usable
        self.assertTrue(dlg.btn_yes.isVisible())
        dlg.close()

    def test_nothing_is_asked_for_when_everything_is_there(self):
        from unittest import mock
        from corpse.gui.training import setup_dialog
        with mock.patch("corpse.functions.training.environment_manager.get_cuda_status",
                        return_value={"install_needed": False, "extras_pending": False}):
            seen = []
            self.assertIsNone(setup_dialog.ask_training_components(None, when_ready=lambda: seen.append(True)))
            self.assertEqual(seen, [True])
            self.assertTrue(setup_dialog.components_ready())


class PerformanceOpenerTest(unittest.TestCase):
    def test_the_showcase_can_open_the_performance_of_the_models(self):
        opened = []
        set_performance_opener(lambda parent: opened.append(parent))
        try:
            self.assertTrue(performance_available())
            w = QWidget()
            open_performance(w)
            self.assertEqual(opened, [w])
        finally:
            set_performance_opener(None)

    def test_the_catalog_of_the_models_shows_the_button(self):
        from types import SimpleNamespace
        from corpse.gui.users.catalog import CatalogWidget
        set_performance_opener(lambda parent: None)
        try:
            session = SimpleNamespace(online=False, client=None, is_guest=False,
                                      can=lambda *_a, **_k: False, username="x")
            models = CatalogWidget(session, "model")
            photos = CatalogWidget(session, "photos")
            self.assertTrue(models.btn_performance.isVisibleTo(models))
            self.assertFalse(photos.btn_performance.isVisibleTo(photos))
        finally:
            set_performance_opener(None)


class WindowSizeTest(unittest.TestCase):
    def test_the_main_window_has_a_usable_floor(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        from corpse.functions.users.session import Session
        from corpse.functions.users.store import LocalStore
        from corpse.gui.home import home_gui
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(home_gui, "WebcamDemoButton", lambda: QWidget()):
                win = home_gui.AppWindow(Session(LocalStore(Path(tmp))))
            screen = QApplication.primaryScreen().availableGeometry()
            try:                     # the floor is lowered only by the screen itself (small laptop, offscreen)
                self.assertGreaterEqual(win.minimumWidth(), min(1120, int(screen.width() * 0.92)))
                self.assertGreaterEqual(win.minimumHeight(), min(720, int(screen.height() * 0.92)))
            finally:
                win.close()
                win.deleteLater()


if __name__ == "__main__":
    unittest.main()
