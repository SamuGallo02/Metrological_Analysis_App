import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from common.ambient.updater import prefs

app = QApplication.instance() or QApplication([])


class FakeSession:
    server_url = "http://10.0.0.5:8765"


class SettingsDialogTest(unittest.TestCase):
    def test_everything_is_in_one_window(self):
        from unittest import mock
        from corpse.gui import settings_dialog as sd
        with mock.patch.object(sd, "HardwareAccelerationWidget", lambda parent=None: sd.QWidget()), \
                mock.patch.object(sd, "LanguageWidget", lambda: sd.QWidget()):
            dlg = sd.SettingsDialog(FakeSession())
        names = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
        self.assertEqual(len(names), 4)
        self.assertIn("10.0.0.5", dlg.server.address.text())

    def test_the_update_mode_is_saved_from_the_settings(self):
        from common.ambient.update_dialog import UpdatesPanel
        with tempfile.TemporaryDirectory() as tmp:
            panel = UpdatesPanel(root=Path(tmp))
            self.assertEqual(prefs.mode(Path(tmp)), "ask")
            panel.mode.setCurrentIndex(panel.mode.findData("auto"))
            self.assertEqual(prefs.mode(Path(tmp)), "auto")


if __name__ == "__main__":
    unittest.main()
