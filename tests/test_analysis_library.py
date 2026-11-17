"""The analysis pages register folders in the library instead of copying them.

Autore: Samuele Gallo
"""
import os, sys, tempfile, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest import mock

import cv2
import numpy as np
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

app = QApplication.instance() or QApplication([])
for name in ("warning", "information", "critical"):
    setattr(QMessageBox, name, staticmethod(lambda *a, **k: None))

from corpse.functions.analysis import library as index
from corpse.functions.analysis.library import Library
from corpse.gui.analysis import library_picker
from corpse.gui.analysis.analysis_gui import StereoAnalysisPage
from corpse.gui.analysis.photo_gui import PhotoAnalysisPage
from corpse.gui.analysis.video_gui import VideoAnalysisPage
from corpse.gui.analysis.video_stereo_gui import VideoStereoAnalysisPage


def snapshot(folder):
    return sorted((str(p.relative_to(folder)), p.stat().st_size) for p in Path(folder).rglob("*"))


class AnalysisLibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lib = Library(self.root / "lib.sqlite")
        self._saved = dict(index.LEGACY_DIRS)
        index.LEGACY_DIRS.update({k: self.root / "app" / k for k in index.KINDS})
        patcher = mock.patch.object(library_picker, "default_library", lambda: self.lib)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.photos = self.root / "usb" / "dive"
        self.photos.mkdir(parents=True)
        cv2.imwrite(str(self.photos / "1.png"), np.zeros((8, 8, 3), np.uint8))

    def tearDown(self):
        index.LEGACY_DIRS.update(self._saved)
        self.lib.close()
        self.tmp.cleanup()

    def choose(self, folder):
        return mock.patch.object(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(folder)))

    def add(self, kind, folder):
        """What "Folders > Local" does: the folder is registered where it is, and the analysis sees it."""
        return self.lib.add_source(kind, folder)

    def test_photo_page_uses_the_folder_in_place(self):
        before = snapshot(self.photos)
        self.add("photo", self.photos)
        page = PhotoAnalysisPage(lambda: None)
        self.assertEqual(page.selected_folder, str(self.photos.resolve()))
        self.assertEqual(snapshot(self.photos), before)
        self.assertEqual(snapshot(self.root / "app") if (self.root / "app").exists() else [], [])   # no copy made
        self.assertEqual(page.folder_combo.currentText(), "dive")

    def test_photo_page_refuses_a_stereo_folder(self):
        """It is registered all the same (it is the user's folder), but this page says it cannot use it."""
        (self.photos / "rx").mkdir()
        (self.photos / "lx").mkdir()
        self.add("photo", self.photos)
        with mock.patch.object(QMessageBox, "warning", staticmethod(lambda *a, **k: None)) as warned:
            page = PhotoAnalysisPage(lambda: None)
        self.assertIsNone(page.selected_folder)

    def test_a_folder_taken_out_of_the_list_leaves_the_files_alone(self):
        src = self.add("video", self.photos)
        page = VideoAnalysisPage(lambda: None)
        self.assertEqual(page.selected_folder, str(self.photos.resolve()))
        self.lib.remove_source(src.id)                 # as "Remove from the list" does in Folders > Local
        page._refresh_datasets()
        self.assertIsNone(page.selected_folder)
        self.assertTrue((self.photos / "1.png").exists())

    def test_a_folder_that_disappeared_cannot_be_run(self):
        self.add("photo_stereo", self.photos)
        page = StereoAnalysisPage(lambda: None)
        (self.photos / "1.png").unlink()
        self.photos.rmdir()
        page._refresh_datasets()
        self.assertIsNone(page.selected_folder)
        self.assertIn("non trovata", page.folder_combo.currentText())

    def test_all_four_pages_have_their_own_kind(self):
        kinds = {c: c.KIND for c in (StereoAnalysisPage, PhotoAnalysisPage, VideoAnalysisPage, VideoStereoAnalysisPage)}
        self.assertEqual(sorted(kinds.values()), sorted(index.KINDS))


if __name__ == "__main__":
    unittest.main()
