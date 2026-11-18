"""The window that improves a photo, and the switch that shows the improved copy in the viewer.

No algorithm is needed: the test registers a method of its own (a copy with a mark in it) and checks what the
interface does around it - which methods it offers, which controls it builds, and where the file ends up.

Autore: Samuele Gallo
"""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage                                      # noqa: E402
from PySide6.QtWidgets import QApplication                            # noqa: E402

from common import image_enhance                                      # noqa: E402
from common.ui.enhance_controls import BeforeAfter, ParamControls     # noqa: E402
from common.ui.media_viewer import MediaViewerDialog                  # noqa: E402

from corpse.gui.users.enhance_dialog import EnhanceDialog             # noqa: E402

app = QApplication.instance() or QApplication([])

PARAMS = [{"name": "sharpen", "label": "Sharpening", "type": "float", "default": 0.2, "min": 0, "max": 1,
           "step": 0.1, "help": "Makes edges crisper."},
          {"name": "white_balance", "label": "Remove colour cast", "type": "bool", "default": True},
          {"name": "style", "label": "Style", "type": "choice", "default": "soft", "choices": ["soft", "hard"]}]


def a_photo(folder: Path, name: str = "a.png") -> Path:
    path = folder / name
    QImage(40, 30, QImage.Format.Format_RGB32).save(str(path))
    return path


def session(online: bool = False):
    return SimpleNamespace(online=online, client=None, is_guest=False, username="x")


class ParamControlsTest(unittest.TestCase):
    def test_a_control_is_built_for_every_setting_of_the_method(self):
        controls = ParamControls()
        controls.set_params(PARAMS)
        values = controls.values()
        self.assertEqual(sorted(values), ["sharpen", "style", "white_balance"])
        self.assertAlmostEqual(values["sharpen"], 0.2, places=3)      # the default is where the slider starts
        self.assertIs(values["white_balance"], True)
        self.assertEqual(values["style"], "soft")

    def test_a_method_without_settings_shows_nothing(self):
        controls = ParamControls()
        controls.set_params(PARAMS)
        controls.set_params(())
        self.assertEqual(controls.values(), {})
        self.assertFalse(controls.isVisible())


class BeforeAfterTest(unittest.TestCase):
    def test_the_divider_follows_where_it_is_put(self):
        view = BeforeAfter()
        view.resize(200, 100)
        view.set_images(QImage(20, 10, QImage.Format.Format_RGB32), QImage(20, 10, QImage.Format.Format_RGB32))
        view._move_to(view.rect().center())
        self.assertAlmostEqual(view.split, 0.5, places=1)
        view._move_to(view.rect().topLeft())
        self.assertEqual(view.split, 0.0)
        view.clear()
        self.assertIsNone(view.before)


class EnhanceDialogTest(unittest.TestCase):
    def setUp(self):
        image_enhance.forget_all()
        image_enhance.register("quick", self._copy, label="Quick contrast", description="A fast one.",
                               params=PARAMS)
        image_enhance.register("deep", self._copy, label="Deep model", problem="weights not downloaded")

    def tearDown(self):
        image_enhance.forget_all()

    settings_seen = {}

    @classmethod
    def _copy(cls, src, dst, params=None):
        """Stands in for a real model: it copies the picture and notes down the settings it was given."""
        shutil.copy2(src, dst)
        cls.settings_seen.clear()
        cls.settings_seen.update(params or {})

    def test_the_methods_are_offered_and_the_unusable_one_is_greyed_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            dlg = EnhanceDialog(session(), a_photo(Path(tmp)))
            dlg._load_methods()
            try:
                self.assertEqual([dlg.methods.itemData(i) for i in range(dlg.methods.count())], ["quick", "deep"])
                self.assertTrue(dlg.methods.model().item(0).isEnabled())
                self.assertFalse(dlg.methods.model().item(1).isEnabled())
                self.assertIn("weights not downloaded", dlg.methods.itemText(1))
                self.assertEqual(dlg.methods.currentData(), "quick")   # the first usable one is chosen
                self.assertEqual(sorted(dlg.params.values()), ["sharpen", "style", "white_balance"])
            finally:
                dlg.deleteLater()

    def test_without_a_server_the_work_is_done_here(self):
        with tempfile.TemporaryDirectory() as tmp:
            dlg = EnhanceDialog(session(online=False), a_photo(Path(tmp)))
            try:
                self.assertTrue(dlg.here.isChecked())
                self.assertFalse(dlg.there.isEnabled())
            finally:
                dlg.deleteLater()

    def test_on_the_server_the_method_is_not_chosen_here(self):
        with tempfile.TemporaryDirectory() as tmp:
            dlg = EnhanceDialog(session(online=True), a_photo(Path(tmp)))
            dlg._load_methods()
            try:
                dlg.there.setChecked(True)
                self.assertFalse(dlg.methods.isEnabled())
                self.assertFalse(dlg.params.isEnabled())
                self.assertFalse(dlg.btn_preview.isEnabled())
                dlg.here.setChecked(True)
                self.assertTrue(dlg.methods.isEnabled())
            finally:
                dlg.deleteLater()

    def test_the_improved_file_is_added_beside_the_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp))
            dlg = EnhanceDialog(session(), photo)
            dlg._load_methods()
            try:
                dlg._ready(dlg._run_here("quick", dlg.params.values()))
                self.assertTrue(dlg.choice.isVisibleTo(dlg))           # the question comes with the result
                self.assertTrue(dlg.btn_keep.isVisibleTo(dlg))
                dlg._keep()
                kept = dlg.kept
                self.assertEqual(kept, photo.parent / "enhanced" / "a.png")
                self.assertTrue(kept.is_file())
                self.assertTrue(photo.is_file())                       # the original is untouched
            finally:
                dlg.deleteLater()

    def test_the_improved_file_can_take_the_place_of_the_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp))
            dlg = EnhanceDialog(session(), photo)
            dlg._load_methods()
            try:
                dlg._ready(dlg._run_here("quick", dlg.params.values()))
                dlg.replace.setChecked(True)                           # chosen with the result on screen
                dlg._keep()
                self.assertEqual(dlg.kept, photo)
                self.assertTrue((photo.parent / "originals" / "a.png").is_file())   # nothing is lost
            finally:
                dlg.deleteLater()

    def test_the_settings_chosen_reach_the_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp))
            dlg = EnhanceDialog(session(), photo)
            dlg._load_methods()
            try:
                out = dlg._run_here("quick", {"sharpen": 0.9})
                self.assertTrue(out.is_file())
                self.assertEqual(self.settings_seen, {"sharpen": 0.9})
            finally:
                dlg.deleteLater()

    def test_the_preview_works_on_a_reduced_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            dlg = EnhanceDialog(session(), a_photo(Path(tmp)))
            dlg._load_methods()
            try:
                before, after = dlg._make_preview("quick", {})
                self.assertFalse(before.isNull())
                self.assertFalse(after.isNull())
                self.assertLessEqual(max(before.width(), before.height()), 900)
            finally:
                dlg.deleteLater()


class ViewerSwitchTest(unittest.TestCase):
    def test_the_switch_appears_only_when_an_improved_copy_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = a_photo(Path(tmp))
            view = MediaViewerDialog(photo)
            try:
                self.assertFalse(view.improved.isVisibleTo(view))
                self.assertEqual(view.shown, photo)
                better = photo.parent / "enhanced" / "a.png"
                better.parent.mkdir()
                QImage(40, 30, QImage.Format.Format_RGB32).save(str(better))
                view.reload()
                self.assertTrue(view.improved.isVisibleTo(view))
                view.improved.setChecked(True)
                self.assertEqual(view.shown, better)                   # the same labels, the other picture
                view.improved.setChecked(False)
                self.assertEqual(view.shown, photo)
            finally:
                view.close()
                view.deleteLater()


if __name__ == "__main__":
    unittest.main()
